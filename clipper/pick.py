"""De beste momenten kiezen: fragmenten die openen met een sterke zin (de hook)."""
import json
import os
import re

import requests

STRONG = {
    "never", "always", "biggest", "worst", "best", "secret", "mistake", "mistakes", "truth", "lie",
    "lies", "nobody", "everyone", "million", "billion", "money", "rich", "broke", "poor", "fail",
    "failed", "failure", "quit", "fired", "wrong", "stop", "rule", "rules", "reason", "why", "how",
    "most", "only", "first", "last", "changed", "lost", "won", "hate", "love", "fear", "afraid",
    "crazy", "insane", "hard", "hardest", "simple", "easy", "free", "debt", "profit", "sales",
    "customers", "business", "founder", "startup", "invest", "wealth", "habit", "habits", "success",
}
WEAK_STARTS = {"and", "but", "so", "because", "or", "then", "also", "yeah", "yes", "no", "right",
               "okay", "ok", "well", "um", "uh", "like", "it", "that", "this", "they", "he", "she",
               "those", "these", "which", "there"}
FILLER = {"um", "uh", "erm", "hmm"}


def clean(word):
    return re.sub(r"[^a-z0-9'$%]", "", word.lower())


def sentences_from_words(words, max_gap=0.9, max_words=45):
    """Woorden groeperen tot zinnen op leestekens of pauzes."""
    sents, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        ends = w["word"].rstrip('"\')').endswith((".", "?", "!"))
        gap = (words[i + 1]["start"] - w["end"]) if i + 1 < len(words) else 99
        if ends or gap > max_gap or len(cur) >= max_words:
            sents.append({"first": cur[0], "last": cur[-1], "start": words[cur[0]]["start"],
                          "end": words[cur[-1]]["end"],
                          "text": " ".join(words[k]["word"] for k in cur)})
            cur = []
    return sents


def hook_score(text):
    toks = [clean(t) for t in text.split()]
    toks = [t for t in toks if t]
    if not toks:
        return -5.0
    score = 0.0
    if toks[0] in WEAK_STARTS:
        score -= 2.5
    if text.strip().endswith("?"):
        score += 1.5
    if any(re.search(r"\d", t) or t.startswith("$") for t in toks):
        score += 1.5
    score += min(3.0, 1.0 * sum(1 for t in toks if t in STRONG))
    if "you" in toks or "your" in toks:
        score += 1.0
    if 4 <= len(toks) <= 16:
        score += 1.0
    elif len(toks) < 3:
        score -= 1.5
    elif len(toks) > 28:
        score -= 1.0
    return score


def body_score(text, duration):
    toks = [clean(t) for t in text.split()]
    toks = [t for t in toks if t]
    if not toks or duration <= 0:
        return -5.0
    score = min(3.0, 0.4 * sum(1 for t in toks if t in STRONG))
    rate = len(toks) / duration            # woorden per seconde: tempo houdt aandacht vast
    if rate < 1.8:
        score -= 1.5
    elif rate > 2.6:
        score += 0.7
    score -= min(2.0, 0.5 * sum(1 for t in toks if t in FILLER))
    return score


def build_candidates(words, min_s=20, max_s=45, target_s=32):
    sents = sentences_from_words(words)
    cands = []
    for i, first in enumerate(sents):
        best = None
        for j in range(i, len(sents)):
            dur = sents[j]["end"] - first["start"]
            if dur > max_s:
                break
            if dur >= min_s:
                ends_well = sents[j]["text"].rstrip('"\')').endswith((".", "?", "!"))
                fit = -abs(dur - target_s) / 10.0 + (0.8 if ends_well else 0.0)
                if best is None or fit > best[0]:
                    best = (fit, j)
        if best is None:
            continue
        j = best[1]
        text = " ".join(s["text"] for s in sents[i:j + 1])
        dur = sents[j]["end"] - first["start"]
        cands.append({
            "first": first["first"], "last": sents[j]["last"],
            "start": first["start"], "end": sents[j]["end"], "duration": dur,
            "hook": first["text"], "text": text,
            "score": 1.6 * hook_score(first["text"]) + body_score(text, dur) + best[0],
        })
    return cands


def non_overlapping(cands, n):
    chosen = []
    for c in sorted(cands, key=lambda x: x["score"], reverse=True):
        if all(c["end"] <= o["start"] or c["start"] >= o["end"] for o in chosen):
            chosen.append(c)
        if len(chosen) >= n:
            break
    return chosen


def fallback_title(hook):
    toks = hook.strip().strip('"').split()
    title = " ".join(toks[:9]).rstrip(",;:-")
    if len(toks) > 9:
        title += "..."
    return title


PROMPT = """You pick moments from a podcast transcript for viral short-form clips (YouTube Shorts,
Instagram Reels). Below are candidate segments. Choose the {n} best ones.

A great clip: opens with a line that makes a stranger stop scrolling (bold claim, number,
surprising confession, question), is understandable without earlier context, stays on one idea and
ends on a finished thought. Reject segments that start mid-thought or are small talk, ads or
sponsor reads.

For each chosen segment write:
- "title": on-screen hook text, max 8 words, punchy, true to what is actually said. No emojis.
- "caption": one short sentence for the post caption, max 110 characters. No hashtags.

Answer with ONLY a JSON array, best first: [{{"id": <number>, "title": "...", "caption": "..."}}]

Candidates:
{items}
"""


def ask_gemini(cands, n, models):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None, "geen GEMINI_API_KEY ingesteld"
    items = "\n".join(f'[{i}] ({c["duration"]:.0f}s) {c["text"][:900]}' for i, c in enumerate(cands))
    body = {"contents": [{"parts": [{"text": PROMPT.format(n=n, items=items)}]}],
            "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}}
    last_error = "onbekend"
    for model in models:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=body, timeout=120)
            if r.status_code != 200:
                last_error = f"{model}: HTTP {r.status_code} {r.text[:150]}"
                continue
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
            picks = json.loads(text)
            if isinstance(picks, dict):
                picks = picks.get("clips") or picks.get("items") or []
            out = []
            for p in picks:
                idx = int(p["id"])
                if 0 <= idx < len(cands) and str(p.get("title", "")).strip():
                    out.append({"idx": idx, "title": str(p["title"]).strip()[:80],
                                "caption": str(p.get("caption", "")).strip()[:140]})
            if out:
                return out, None
            last_error = f"{model}: leeg antwoord"
        except Exception as e:  # noqa: BLE001
            last_error = f"{model}: {str(e)[:150]}"
    return None, last_error


def pick_clips(words, n, min_s=20, max_s=45, models=None):
    """Geeft (clips, opmerking). Elke clip: start, end, first, last, title, caption."""
    cands = build_candidates(words, min_s, max_s)
    if not cands:
        return [], "geen bruikbare fragmenten gevonden"
    shortlist = non_overlapping(cands, 24)
    shortlist.sort(key=lambda c: c["start"])
    note = None
    picks, err = ask_gemini(shortlist, n, models or [])
    clips = []
    if picks:
        for p in picks:
            c = dict(shortlist[p["idx"]])
            if all(c["end"] <= o["start"] or c["start"] >= o["end"] for o in clips):
                c["title"], c["caption"] = p["title"], p["caption"]
                clips.append(c)
            if len(clips) >= n:
                break
    if len(clips) < n:
        if err:
            note = f"AI-keuze niet gelukt ({err}); gekozen met de ingebouwde regels."
        for c in non_overlapping(cands, n * 3):
            if len(clips) >= n:
                break
            if all(c["end"] <= o["start"] or c["start"] >= o["end"] for o in clips):
                c = dict(c)
                c["title"], c["caption"] = fallback_title(c["hook"]), ""
                clips.append(c)
    return clips, note
