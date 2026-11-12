"""Campagnes automatisch zoeken: leest het openbare overzicht van Content Rewards, kiest de beste
campagne voor deze niche en zet de bron en de verplichte tekst klaar.

Let op: de site heeft geen officiele API. Dit leest de gegevens die in de openbare pagina
(contentrewards.com/discover) zitten. Als de site verandert, meldt de bot dat in Telegram met een
korte diagnose zodat de lezer aangepast kan worden."""
import json
import re

import requests

from . import tg
from .common import now_utc

SITE = "https://contentrewards.com"
BOARD_URL = SITE + "/discover"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
URL_RX = re.compile(r"https?://[^\s\"'<>\\)\]]+")
YT_RX = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com/(?:@|channel/|c/|user/|watch\?|playlist\?)"
                   r"|youtu\.be/)[^\s\"'<>\\)\]]+", re.I)
PLATFORMS = {"tiktok", "instagram", "youtube", "x", "twitter", "facebook"}
BAD = re.compile(r"casino|gambl|betting|\bbets?\b|sportsbook|poker|slots?\b|crypto|memecoin|\btokens?\b|"
                 r"\bnft|forex|binary option|nsfw|onlyfans|18\+|adult|escort|dating", re.I)
GOOD = re.compile(r"business|entrepreneur|founder|startup|podcast|interview|money|invest|sales|marketing|"
                  r"career|self.?improvement|education|leadership|mindset|productivity|\btech\b|\bai\b", re.I)


# ---------- de pagina uitlezen ----------

def fetch_html(url=BOARD_URL):
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en"}, timeout=45)
    r.raise_for_status()
    return r.text


def json_blobs(html):
    """Alle JSON die in de pagina zit (Next.js zet de gegevens in scripts)."""
    for m in re.finditer(r'<script[^>]*type="application/(?:ld\+)?json"[^>]*>(.*?)</script>', html, re.S):
        try:
            yield json.loads(m.group(1))
        except ValueError:
            pass
    for m in re.finditer(r'self\.__next_f\.push\(\[\d+,\s*"((?:[^"\\]|\\.)*)"\]\)', html, re.S):
        try:
            chunk = json.loads('"' + m.group(1) + '"')
        except ValueError:
            continue
        for line in chunk.split("\n"):
            _, sep, rest = line.partition(":")
            rest = rest.strip()
            if sep and rest[:1] in ("[", "{"):
                try:
                    yield json.loads(rest)
                except ValueError:
                    pass


def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def flatten(d, prefix="", depth=0, out=None):
    out = {} if out is None else out
    for k, v in d.items():
        key = f"{prefix}{k}".lower()
        if isinstance(v, dict) and depth < 2:
            flatten(v, key + ".", depth + 1, out)
        else:
            out[key] = v
    return out


NUM_RX = re.compile(r"^\s*\$*\s*([\d,]+(?:\.\d+)?)\s*([km])?\s*(?:usd)?\s*$", re.I)


def num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = NUM_RX.match(v)
        if m:
            n = float(m.group(1).replace(",", ""))
            return n * {"k": 1e3, "m": 1e6}.get((m.group(2) or "").lower(), 1)
    return None


# Veldnamen zoals Content Rewards ze gebruikt (gezien via /debug op 13 nov 2026).
KNOWN = {
    "cpm": ["ratePer1kRaw", "ratePer1k", "ratePer1kLabel", "payoutSortRaw"],
    "total": ["budgetTotalRaw", "budgetTotal", "budgetTotalLabel"],
    "spent": ["budgetSpentRaw", "budgetSpent", "budgetSpentLabel"],
    "left": ["availableBudgetRaw", "availableBudget"],
    "creators": ["creatorCountRaw", "creatorCount"],
    "progress": ["progressPercentage"],
}


def known(d, field):
    for k in KNOWN[field]:
        n = num(d.get(k))
        if n is not None:
            return n
    return None


def find(flat, include, exclude="", want="num"):
    inc = re.compile(include)
    exc = re.compile(exclude) if exclude else None
    for k, v in flat.items():
        if inc.search(k) and not (exc and exc.search(k)):
            if want == "num":
                n = num(v)
                if n is not None:
                    return n
            elif want == "str":
                if isinstance(v, str) and v.strip():
                    return v.strip()
            elif want == "bool":
                if isinstance(v, bool):
                    return v
    return None


def platforms_of(flat):
    found = set()
    for k, v in flat.items():
        if "platform" in k or k.endswith("payouts"):
            for item in (v if isinstance(v, list) else [v]):
                if isinstance(item, dict):
                    item = item.get("platform") or item.get("name") or item.get("type")
                if isinstance(item, str) and item.lower() in PLATFORMS:
                    found.add("x" if item.lower() == "twitter" else item.lower())
    return found


def creators_of(flat):
    for k, v in flat.items():
        if re.search(r"creatorcount|creators|participants|clippers", k) and "max" not in k:
            if isinstance(v, list):
                return float(len(v))
            n = num(v)
            if n is not None:
                return n
    return None


RATE_KEY = re.compile(r"rate|cpm|thousand|1k|1000|reward|payout|price|amount", re.I)
RATE_BAD = re.compile(r"min|max|cap|limit|submission|total|budget|count|paid|spent|viewcount", re.I)


def payout_rates(d):
    """Tarieven per platform uit lijsten zoals payouts: [{platform, rate, ...}]."""
    out = []

    def scan(o, depth=0):
        for k, v in o.items():
            if isinstance(v, list) and v and all(isinstance(i, dict) for i in v) \
                    and re.search(r"payout|rate|reward|platform|cpm", k, re.I):
                for item in v:
                    plat = next((str(item[x]).lower() for x in ("platform", "name", "type")
                                 if isinstance(item.get(x), str)), "")
                    for kk, vv in item.items():
                        if RATE_KEY.search(kk) and not RATE_BAD.search(kk):
                            n = num(vv)
                            if n is not None:
                                out.append((plat, n))
                                break
            elif isinstance(v, dict) and depth < 2:
                scan(v, depth + 1)

    scan(d)
    return out


def normalize(d):
    """Maakt van een stukje JSON een campagne, of None als het geen campagne lijkt."""
    cid = next((d[k] for k in ("id", "campaignId", "campaign_id", "uuid")
                if isinstance(d.get(k), str) and UUID.match(d[k])), None)
    if not cid:
        return None
    flat = flatten(d)
    title = find(flat, r"(^|\.)(title|name|campaignname)$", want="str")
    if not title:
        return None
    cpm = known(d, "cpm")
    if cpm is None:
        cpm = find(flat, r"cpm|perthousand|per1k|per_1k|per1000|rewardrate|payoutrate|rateper|(^|\.)rate$|reward",
                   r"creator|success|engage|ratio|spent|budget|limit|total|max|min|paid|submission|viewcount|count|id$")
        rates = payout_rates(d)
        mine = [r for p, r in rates if p in ("youtube", "instagram")] or [r for _, r in rates]
        if mine:
            cpm = min(mine)
    if cpm is not None and cpm > 60:          # waarschijnlijk in centen
        cpm = cpm / 100 if cpm / 100 <= 60 else None
    total = known(d, "total")
    if total is None:
        total = find(flat, r"budget|funded", r"spent|left|remain|avail|used|paid|progress|pct|percent|burn|daily|per")
    spent = known(d, "spent")
    if spent is None:
        spent = find(flat, r"spent|paidout|used", r"rate|per|pct|percent|progress")
    left = known(d, "left")
    if left is None:
        left = find(flat, r"left|remaining|available", r"day|time|runway")
    prog = known(d, "progress")
    if prog is None:
        prog = find(flat, r"progress|percent|pct")
    if prog is not None and prog <= 1:
        prog *= 100
    if left is None and total is not None and spent is not None:
        left = max(0.0, total - spent)
    if left is None and total is not None and prog is not None:
        left = total * (1 - prog / 100)
    if prog is None and total and left is not None:
        prog = 100 * (1 - left / total)
    if cpm is None and total is None:
        return None
    desc = ""
    for k, v in flat.items():
        if re.search(r"description|rules|brief|requirement|instruction|guideline|terms", k) \
                and isinstance(v, str) and len(v) > len(desc):
            desc = v
    blob = json.dumps(d, ensure_ascii=False)
    urls = list(dict.fromkeys(u.rstrip(".,;") for u in URL_RX.findall(desc + " " + blob)))
    youtube = list(dict.fromkeys(u.rstrip(".,;") for u in YT_RX.findall(desc + " " + blob)))
    ctype = (find(flat, r"(^|\.)(campaigntype|contenttype|kind)$", want="str")
             or find(flat, r"(^|\.)type$", want="str") or "").lower()
    if ctype in ("cpm", "pool", "perpost"):     # dat is de betaalvorm, niet het soort content
        ctype = ""
    status = (find(flat, r"(^|\.)status$", want="str") or "").lower()
    return {
        "id": cid, "title": title, "url": f"{SITE}/discover/{cid}", "cpm": cpm,
        "budget_total": total, "budget_left": left, "progress": prog,
        "creators": known(d, "creators") if known(d, "creators") is not None else creators_of(flat), "platforms": sorted(platforms_of(flat)),
        "type": ctype, "status": status,
        "category": find(flat, r"category", want="str") or "",
        "requires_application": find(flat, r"requiresapplication|applicationrequired|needsapproval|"
                                           r"requiresapproval", want="bool"),
        "description": desc[:3000], "youtube": youtube, "links": urls[:12],
        "_fields": sum(x is not None for x in (cpm, total, left, desc or None)),
    }


def parse_board(html):
    found = {}
    for blob in json_blobs(html):
        for d in walk(blob):
            c = normalize(d) if isinstance(d, dict) else None
            if c and (c["id"] not in found or c["_fields"] > found[c["id"]]["_fields"]):
                found[c["id"]] = c
    return list(found.values())


def diagnose(html):
    blobs = list(json_blobs(html))
    cands = [d for b in blobs for d in walk(b) if isinstance(d, dict)
             and any(isinstance(v, str) and UUID.match(v) for v in d.values())]
    sample = max(cands, key=len) if cands else None
    keys = ", ".join(sorted(sample)[:25]) if sample else "-"
    return (f"pagina {len(html) // 1000} kB, {len(blobs)} JSON-blokken, {len(cands)} mogelijke "
            f"campagnes. Voorbeeldvelden: {keys}")


def raw_campaigns(html):
    found = {}
    for blob in json_blobs(html):
        for d in walk(blob):
            c = normalize(d) if isinstance(d, dict) else None
            if c and (c["id"] not in found or len(d) > len(found[c["id"]])):
                found[c["id"]] = d
    return found


def describe_fields(d, limit=3300):
    """Korte lijst van velden en voorbeeldwaarden, om de lezer te kunnen afstellen."""
    lines = []

    def show(prefix, o, depth):
        for k, v in o.items():
            key = f"{prefix}{k}"
            if isinstance(v, dict) and depth < 2:
                show(key + ".", v, depth + 1)
            elif isinstance(v, list):
                if v and isinstance(v[0], dict):
                    lines.append(f"{key}: lijst van {len(v)}, eerste: " + json.dumps(v[0], ensure_ascii=False)[:170])
                else:
                    lines.append(f"{key}: lijst van {len(v)}")
            else:
                lines.append(f"{key}: {str(v)[:45]}")

    show("", d, 0)
    c = normalize(d) or {}
    lines.append(f"-> gelezen tarief: {c.get('cpm')}; YouTube-links: {c.get('youtube')}; "
                 f"andere links: {[u for u in c.get('links', []) if u not in c.get('youtube', [])][:4]}")
    return "\n".join(lines)[:limit]


def describe_sources(c, site_links=frozenset()):
    try:
        html = fetch_text(detail_url(c))
    except Exception as e:  # noqa: BLE001
        return f"Campagnepagina niet te openen: {str(e)[:150]}"
    links = [(k, u) for k, u in page_links(html) if u not in site_links]
    srcs, _ = find_sources(c, site_links)
    lines = [f"Campagnepagina: {len(html) // 1000} kB, {len(links)} links."]
    lines += [f"{k}: {u[:90]}" for k, u in links[:25]]
    lines.append(f"-> gevonden bronnen: {srcs[:5] or 'geen'}")
    return "\n".join(lines)[:3300]


# ---------- bronnen op de campagnepagina ----------

STR_FIELD = re.compile(r'"([A-Za-z_][\w]*)"\s*:\s*"((?:[^"\\]|\\.)*)"')
SKIP_KEY = re.compile(r"top|best|submission|earner|avatar|thumbnail|logo|image|banner|icon|profile|social|"
                      r"footer|og|meta|preview|cover", re.I)
DOC_RX = re.compile(r"https?://(?:docs\.google\.com/(?:document|spreadsheets)/d/[\w-]+|"
                    r"[\w.-]*notion\.(?:site|so)/[^\s\"'<>\\)\]]+)", re.I)
DRIVE_RX = re.compile(r"https?://drive\.google\.com/(?:drive/(?:u/\d+/)?folders/|file/d/)[\w-]+", re.I)


def fetch_text(url):
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en"}, timeout=45)
    r.raise_for_status()
    return r.text


def _unescape(text):
    for a, b in (("\\u002F", "/"), ("\\u0026", "&"), ("\\u003d", "="), ("\\/", "/")):
        text = text.replace(a, b)
    return text


def string_fields(html):
    """Alle (sleutel, tekst)-paren uit de pagina, ook uit ingepakte Next.js-gegevens."""
    variants = [html, html.replace('\\"', '"').replace("\\\\", "\\")]
    out = []
    for text in variants:
        for m in STR_FIELD.finditer(text):
            out.append((m.group(1), _unescape(m.group(2))))
    return out


def clean_url(u):
    return u.rstrip(".,;:!?'\"")


def youtube_ok(u):
    return "/shorts/" not in u and "contentrewards" not in u.lower() and "whop" not in u.lower()


def page_links(html):
    """(sleutel, url) voor alle links op een pagina, behalve opmaak en clips van andere clippers."""
    found = []
    for key, val in string_fields(html):
        if SKIP_KEY.search(key):
            continue
        for u in URL_RX.findall(val):
            found.append((key, clean_url(u)))
    return list(dict.fromkeys(found))


def youtube_in_doc(url):
    """Een gedeeld Google Doc, Sheet of Notion-pagina openen en de YouTube-links eruit halen."""
    m = re.search(r"docs\.google\.com/(document|spreadsheets)/d/([\w-]+)", url)
    if m:
        kind, doc_id = m.groups()
        fmt = "txt" if kind == "document" else "csv"
        url = f"https://docs.google.com/{kind}/d/{doc_id}/export?format={fmt}"
    try:
        text = _unescape(fetch_text(url))
    except Exception as e:  # noqa: BLE001 - niet openbaar of niet bereikbaar
        print("Document niet te openen:", url, str(e)[:100])
        return []
    return [clean_url(u) for u in YT_RX.findall(text) if youtube_ok(u)]


def detail_url(c):
    return f"{SITE}/discover/{c['id']}"


def find_sources(c, site_links=frozenset()):
    """Zoekt de bronvideo's van een campagne: eerst in de gegevens, dan op de campagnepagina en in
    gelinkte documenten. Geeft (bronnen, tekst van de pagina) terug."""
    sources = [u for u in c.get("youtube", []) if youtube_ok(u)]
    text = c.get("description", "")
    try:
        html = fetch_text(detail_url(c))
    except Exception as e:  # noqa: BLE001
        print("Campagnepagina niet te openen:", c["title"], str(e)[:100])
        return list(dict.fromkeys(sources)), text
    links = [(k, u) for k, u in page_links(html) if u not in site_links]
    for k, v in string_fields(html):
        if re.search(r"description|rules|requirement|brief|guideline|instruction", k, re.I) and len(v) > len(text):
            text = v
    sources += [u for _, u in links if YT_RX.match(u) and youtube_ok(u)]
    docs = list(dict.fromkeys(u for _, u in links if DOC_RX.match(u)))[:4]
    for doc in docs:
        sources += youtube_in_doc(doc)
    if not sources:
        sources += list(dict.fromkeys(u for _, u in links if DRIVE_RX.match(u)))[:3]
    return list(dict.fromkeys(sources))[:12], text


# ---------- kiezen ----------

def settings(cfg):
    base = {"enabled": True, "min_cpm": 1.0, "min_budget_left": 1500, "max_progress_pct": 85,
            "max_creators": 400, "require_open": True, "platforms": ["youtube", "instagram"]}
    base.update(cfg.get("campaign_finder") or {})
    return base


EN_WORDS = {"the", "and", "to", "of", "a", "in", "is", "for", "you", "your", "our", "with", "on", "that",
            "this", "be", "are", "as", "it", "at", "by", "or", "from", "will", "must", "use", "we", "can"}


def english_enough(text):
    """Grof: Engelse stopwoorden moeten voorkomen, en geen niet-Latijns schrift."""
    letters = [ch for ch in text if ch.isalpha()]
    if letters and sum(1 for ch in letters if ord(ch) < 0x250) / len(letters) < 0.9:
        return False
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if len(words) < 8:
        return True                   # te weinig tekst om te beoordelen
    return sum(w in EN_WORDS for w in words) / len(words) >= 0.07


def eligible(c, f, soft=False):
    """Geeft (ok, reden). soft = ruimere grenzen, voor een campagne waar je al in zit."""
    if c["status"] and c["status"] not in ("active", "live", "open", "running"):
        return False, f"status {c['status']}"
    if "ugc" in c["type"] and "clip" not in c["type"]:
        return False, "geen clipcampagne"
    if c["platforms"] and not set(c["platforms"]) & set(f["platforms"]):
        return False, "geen YouTube of Instagram"
    if f["require_open"] and c["requires_application"] and not soft:
        return False, "aanvraag nodig"
    if c["cpm"] is not None and c["cpm"] < (0.5 if soft else f["min_cpm"]):
        return False, "tarief te laag"
    floor = 400 if soft else f["min_budget_left"]
    if c["budget_left"] is not None and c["budget_left"] < floor:
        return False, "budget bijna op"
    if c["progress"] is not None and c["progress"] > (95 if soft else f["max_progress_pct"]):
        return False, "budget bijna op"
    if c["creators"] is not None and c["creators"] > f["max_creators"] and not soft:
        return False, "te veel clippers"
    head = f"{c['title']} {c['category']} {c['description'][:200]}"
    if BAD.search(head):
        return False, "gokken, crypto of volwassen"
    if not english_enough(f"{c['title']} {c['description'][:400]}"):
        return False, "niet Engelstalig"
    return True, ""


def score(c):
    s = 0.35 * min((c["cpm"] or 0) / 5, 1)
    s += 0.30 * (min(c["budget_left"] / 25000, 1) if c["budget_left"] is not None else 0.3)
    s += 0.20 * (1 - min(c["creators"] / 300, 1) if c["creators"] is not None else 0.5)
    s += 0.15 * (1.0 if GOOD.search(f"{c['title']} {c['category']} {c['description'][:300]}") else 0.0)
    if c["youtube"]:
        s += 0.15        # bronmateriaal dat de bot kan downloaden
    if set(c["platforms"]) >= {"youtube", "instagram"}:
        s += 0.05
    return round(s, 3)


def rank(board, f, skip_ids=()):
    ok = [c for c in board if c["id"] not in skip_ids and eligible(c, f)[0]]
    if not ok:      # niets over: iets ruimer zoeken (lager tarief, meer clippers)
        loose = dict(f, min_cpm=min(f["min_cpm"], 0.5), max_creators=max(f["max_creators"], 1500))
        ok = [c for c in board if c["id"] not in skip_ids and eligible(c, loose)[0]]
    return sorted(ok, key=score, reverse=True)


def with_sources(ranked, site_links, limit=10):
    """De beste campagnes waarvan de bot de bron zelf kan vinden, in volgorde."""
    good = []
    for c in ranked[:limit]:
        srcs, text = find_sources(c, site_links)
        if srcs:
            good.append(dict(c, sources=srcs, description=text[:3000]))
        if len(good) >= 3:
            break
    return good


# ---------- regels van de campagne ----------

RULES_PROMPT = """Read this clipping campaign description. Answer ONLY with JSON:
{{"required_text": "hashtags and @mentions that EVERY post must contain, exactly as written, separated by spaces, or empty if none are required",
"summary": "max 3 short lines in Dutch: what footage may be used, what is forbidden, special demands"}}

Description:
{desc}"""


def extract_rules(desc, cfg):
    import os
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key or len(desc) < 30:
        return {}
    body = {"contents": [{"parts": [{"text": RULES_PROMPT.format(desc=desc[:3000])}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}}
    for model in cfg.get("gemini_models", []):
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                              headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                              json=body, timeout=90)
            if r.status_code != 200:
                continue
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())
            req = " ".join(t for t in str(data.get("required_text", "")).split() if t[:1] in "#@")
            return {"required_text": req, "summary": str(data.get("summary", "")).strip()[:500]}
        except Exception as e:  # noqa: BLE001
            print("Regels uitlezen mislukt:", str(e)[:150])
    return {}


# ---------- kiezen en klaarzetten ----------

def money(v):
    return "onbekend" if v is None else f"${v:,.0f}"


def line(c):
    cpm = f"${c['cpm']:.2f}" if c["cpm"] is not None else "tarief onbekend"
    return f"{c['title']}  ({cpm} per 1.000 views, budget over: {money(c['budget_left'])})"


def apply_campaign(state, cfg, c, options=None, notify=True):
    if not c.get("sources"):
        srcs, text = find_sources(c)
        c = dict(c, sources=srcs, description=text[:3000])
    rules = extract_rules(c.get("description", ""), cfg)
    sources = c["sources"][:6]
    state["campaign"] = {"id": c["id"], "title": c["title"], "url": c["url"], "cpm": c["cpm"],
                         "budget_left": c["budget_left"], "platforms": c["platforms"],
                         "chosen": now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")}
    state["campaign_options"] = [{k: v for k, v in o.items() if k != "_fields"}
                                 | {"description": o["description"][:1500]} for o in (options or [c])]
    state["sources"] = sources
    if rules.get("required_text"):
        state["campaign_text"] = rules["required_text"]
    if not notify:
        return
    msg = [f"🎯 Campagne gekozen: {line(c)}",
           f"Platforms: {', '.join(c['platforms']) or 'onbekend'}", "",
           f"Doe dit één keer (1 minuut): open {c['url']} en meld je aan met je account. "
           "Clips plaats ik pas als jij ✅ tikt, dus doe dit eerst."]
    msg.append("Bronnen voor de clips (van de campagnepagina): " + (", ".join(sources) if sources else
               "niet gevonden. Kies een andere campagne met /kies of /zoek."))
    if rules.get("required_text"):
        msg.append(f"Verplichte tekst onder elke post (opgeslagen): {rules['required_text']}")
    if rules.get("summary"):
        msg += ["", "Regels:", rules["summary"]]
    others = (options or [])[1:3]
    if others:
        msg += ["", "Andere opties (kies met /kies <nummer>):"]
        msg += [f"{i}. {line(o)}" for i, o in enumerate(others, 2)]
    tg.send_message("\n".join(msg))


def ensure_campaign(state, cfg, force=False):
    """Zorgt dat er een goede campagne is. Geeft True als er een nieuwe is gekozen."""
    f = settings(cfg)
    if not f["enabled"] or (not state.get("auto_campaign", True) and not force):
        return False
    cur = state.get("campaign")
    try:
        html = fetch_html()
        board = parse_board(html)
    except Exception as e:  # noqa: BLE001
        print("Overzicht ophalen mislukt:", e)
        if force or not cur:
            tg.send_message(f"Het campagne-overzicht ophalen is mislukt: {str(e)[:200]}")
        return False
    if not board:
        if force or not cur:
            tg.send_message("Ik kon geen campagnes uit het overzicht halen, waarschijnlijk is de site "
                            "veranderd. Stuur dit bericht naar Claude zodat de lezer wordt aangepast:\n"
                            + diagnose(html))
        return False
    if cur and not force:
        fresh = next((c for c in board if c["id"] == cur["id"]), None)
        if fresh is None or eligible(fresh, f, soft=True)[0]:
            if fresh:
                cur["budget_left"] = fresh["budget_left"]
            return False            # campagne loopt nog (of staat buiten de eerste pagina): houden
    ranked = rank(board, f, skip_ids={cur["id"]} if (cur and not force) else ())
    site_links = frozenset(u for _, u in page_links(html))
    good = with_sources(ranked, site_links)
    if not good:
        if force or not cur:
            tg.send_message(f"Ik zag {len(board)} campagnes. {len(ranked)} voldoen aan je eisen (Engels, "
                            "YouTube of Instagram, zonder aanvraag, genoeg budget, geen gokken of crypto), "
                            "maar bij geen van de beste 10 kon ik de bronvideo's zelf vinden. Stuur /debug "
                            "voor de details.")
        return False
    ranked = good
    if cur and not force:
        tg.send_message(f"De campagne '{cur['title']}' is bijna of helemaal op. Ik ga over naar een nieuwe.")
    apply_campaign(state, cfg, ranked[0], ranked[:3])
    return True
