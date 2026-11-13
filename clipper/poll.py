"""Elke 15 minuten: jouw tikken en opdrachten in Telegram verwerken en clips inplannen."""
import sys
import traceback

import requests

from . import buffer_api, campaigns, tg
from .common import fmt_local, load_config, load_state, next_slot, pages_base_url, save_state

HELP = ("Opdrachten:\n"
        "/plaats  alle wachtende clips inplannen\n"
        "/weg  alle wachtende clips weggooien\n"
        "/zoek  nu de beste campagne zoeken\n"
        "/debug  velden van de gekozen campagne tonen (voor Claude)\n"
        "/campagne  huidige campagne en alternatieven tonen\n"
        "/kies <nummer>  een van de alternatieven kiezen\n"
        "/auto aan|uit  automatisch campagnes kiezen\n"
        "/bron <link>  zelf een bron toevoegen (zet automatisch kiezen uit)\n"
        "/bronnen  alle bronnen tonen\n"
        "/wisbron <nummer>  bron verwijderen\n"
        "/tekst <tekst>  verplichte campagnetekst of tags voor onder elke post\n"
        "/status  overzicht van wachtende en ingeplande clips")


def post_text(clip, state, cfg):
    parts = [clip.get("caption") or clip["title"], state.get("campaign_text", ""), cfg["caption_suffix"]]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def is_online(url):
    try:
        r = requests.head(url, timeout=30, allow_redirects=False)
        return r.status_code == 200
    except requests.RequestException:
        return False


def approve(clip_id, clip, state, cfg):
    """Plant de clip in. Geeft de tekst terug die onder de video in Telegram komt."""
    channels = cfg["channels"]
    if not channels:
        raise RuntimeError("Er zijn geen Buffer-kanalen ingesteld in config.yml.")
    url = f"{pages_base_url()}/clips/{clip['file']}"
    if not is_online(url):
        raise RuntimeError("De clip staat nog niet online. Tik over een kwartier nog een keer.")
    due = clip.get("due") or next_slot(state, cfg)
    done = clip.setdefault("posts", {})
    failed = []
    for ch in channels:
        if ch["service"] in done:
            continue
        try:
            done[ch["service"]] = buffer_api.schedule_video(
                ch, post_text(clip, state, cfg), clip["title"], url, due, cfg["youtube_category"])
        except Exception as e:  # noqa: BLE001
            failed.append(f"{ch['service']}: {str(e)[:250]}")
    if done:
        clip["status"], clip["due"] = "scheduled", due
    if failed and not done:
        raise RuntimeError("Inplannen mislukt.\n" + "\n".join(failed))
    text = f"✅ Ingepland voor {fmt_local(due, cfg)} op {', '.join(sorted(done))}\n{clip['title']}"
    if failed:
        text += "\n\nNiet gelukt:\n" + "\n".join(failed)
    return text


def handle_callback(cb, state, cfg):
    data = cb.get("data", "")
    action, _, clip_id = data.partition(":")
    clip = state["clips"].get(clip_id)
    if not clip:
        tg.answer_callback(cb["id"], "Deze clip ken ik niet meer.")
        return
    if clip["status"] in ("scheduled", "rejected"):
        tg.answer_callback(cb["id"], "Al verwerkt.")
        return
    if action == "no":
        clip["status"] = "rejected"
        tg.answer_callback(cb["id"], "Weggegooid")
        tg.edit_caption(clip["message_id"], f"❌ Weggegooid\n{clip['title']}")
    elif action == "ok":
        try:
            text = approve(clip_id, clip, state, cfg)
            tg.answer_callback(cb["id"], "Ingepland")
            tg.edit_caption(clip["message_id"], text)
        except Exception as e:  # noqa: BLE001
            tg.answer_callback(cb["id"], "Niet gelukt")
            tg.send_message(f"'{clip['title']}' kon niet worden ingepland:\n{str(e)[:700]}")


def handle_message(msg, state, cfg):
    text = (msg.get("text") or "").strip()
    cmd, _, arg = text.partition(" ")
    cmd, arg = cmd.lower().split("@")[0], arg.strip()
    if cmd == "/zoek":
        tg.send_message("Ik ga zoeken...")
        if not campaigns.ensure_campaign(state, cfg, force=True):
            pass                      # de reden is al in Telegram gemeld
    elif cmd == "/debug":
        try:
            html = campaigns.fetch_html()
            raw = campaigns.raw_campaigns(html)
            cid = (state.get("campaign") or {}).get("id")
            d = raw.get(cid) or next(iter(raw.values()), None)
            if not d:
                tg.send_message("Geen campagnes gevonden. " + campaigns.diagnose(html))
            else:
                tg.send_message("Velden van de campagne:\n" + campaigns.describe_fields(d))
                site = frozenset(u for _, u in campaigns.page_links(html))
                tg.send_message(campaigns.describe_sources(campaigns.normalize(d), site))
        except Exception as e:  # noqa: BLE001
            tg.send_message(f"Mislukt: {str(e)[:300]}")
    elif cmd == "/campagne":
        cur = state.get("campaign")
        if not cur:
            tg.send_message("Nog geen campagne gekozen. Stuur /zoek.")
        else:
            lines = [f"Nu: {campaigns.line(cur)}", cur["url"], "Bronnen: " + (", ".join(state["sources"]) or "geen")]
            lines += [f"{i}. {campaigns.line(o)}" for i, o in enumerate(state.get("campaign_options", []), 1)]
            tg.send_message("\n".join(lines))
    elif cmd == "/kies" and arg.isdigit() and 1 <= int(arg) <= len(state.get("campaign_options", [])):
        opts = state["campaign_options"]
        campaigns.apply_campaign(state, cfg, opts[int(arg) - 1], opts)
    elif cmd == "/auto":
        state["auto_campaign"] = arg.lower() != "uit"
        tg.send_message("Automatisch campagnes kiezen staat " + ("aan." if state["auto_campaign"] else "uit."))
    elif cmd == "/bron" and arg.startswith("http"):
        if arg not in state["sources"]:
            state["sources"].append(arg)
        state["auto_campaign"] = False
        tg.send_message(f"Bron toegevoegd. Je hebt nu {len(state['sources'])} bron(nen). Automatisch "
                        "campagnes kiezen staat nu uit; zet het weer aan met /auto aan. "
                        "De eerste clips komen na de volgende nachtelijke ronde.")
    elif cmd == "/bronnen":
        lines = [f"{i}. {s}" for i, s in enumerate(state["sources"], 1)]
        tg.send_message("\n".join(lines) or "Nog geen bronnen. Stuur /zoek of /bron <link>")
    elif cmd == "/wisbron" and arg.isdigit() and 1 <= int(arg) <= len(state["sources"]):
        removed = state["sources"].pop(int(arg) - 1)
        tg.send_message(f"Verwijderd: {removed}")
    elif cmd == "/tekst":
        state["campaign_text"] = arg
        tg.send_message("Campagnetekst opgeslagen." if arg else "Campagnetekst leeggemaakt.")
    elif cmd in ("/plaats", "/weg"):
        pending = [(cid, c) for cid, c in state["clips"].items() if c["status"] == "pending"]
        if not pending:
            tg.send_message(f"Er wachten geen clips op jouw keuze ({len(state['clips'])} clips in totaal bekend).")
        for cid, c in pending:
            if cmd == "/weg":
                c["status"] = "rejected"
                tg.edit_caption(c["message_id"], f"❌ Weggegooid\n{c['title']}")
                continue
            try:
                text = approve(cid, c, state, cfg)
                tg.edit_caption(c["message_id"], text)
                tg.send_message(text)
            except Exception as e:  # noqa: BLE001
                tg.send_message(f"'{c['title']}' kon niet worden ingepland:\n{str(e)[:700]}")
        if cmd == "/weg" and pending:
            tg.send_message(f"{len(pending)} clip(s) weggegooid.")
    elif cmd == "/status":
        clips = state["clips"].values()
        pending = sum(1 for c in clips if c["status"] == "pending")
        sched = sorted((c["due"], c["title"]) for c in clips if c["status"] == "scheduled")
        cur = state.get("campaign")
        lines = [f"Campagne: {cur['title'] if cur else 'nog geen'}",
                 f"Wacht op jouw keuze: {pending}", f"Bronnen: {len(state['sources'])}", "",
                 "Laatst ingepland:"]
        lines += [f"{fmt_local(d, cfg)}  {t}" for d, t in sched[-6:]] or ["nog niets"]
        tg.send_message("\n".join(lines))
    else:
        tg.send_message(HELP)


def main():
    cfg, state = load_config(), load_state()
    updates = tg.get_updates(state.get("tg_offset", 0))
    owner = str(tg.chat_id())
    for up in updates:
        state["tg_offset"] = up["update_id"] + 1
        print("update:", ", ".join(k for k in up if k != "update_id"),
              (up.get("message") or {}).get("text", "") or (up.get("callback_query") or {}).get("data", ""))
        try:
            if "callback_query" in up:
                cb = up["callback_query"]
                if str(cb.get("from", {}).get("id")) == owner or \
                        str(cb.get("message", {}).get("chat", {}).get("id")) == owner:
                    handle_callback(cb, state, cfg)
            elif "message" in up:
                msg = up["message"]
                if str(msg.get("chat", {}).get("id")) == owner:
                    handle_message(msg, state, cfg)
        except Exception:  # noqa: BLE001 - één kapotte update mag de rest niet blokkeren
            traceback.print_exc()
        save_state(state)
    print(f"{len(updates)} update(s) verwerkt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
