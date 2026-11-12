"""Elke 15 minuten: jouw tikken en opdrachten in Telegram verwerken en clips inplannen."""
import sys
import traceback

import requests

from . import buffer_api, tg
from .common import fmt_local, load_config, load_state, next_slot, pages_base_url, save_state

HELP = ("Opdrachten:\n"
        "/bron <link>  bron toevoegen (kanaal, playlist of video van je campagne)\n"
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
    if cmd == "/bron" and arg.startswith("http"):
        if arg not in state["sources"]:
            state["sources"].append(arg)
        tg.send_message(f"Bron toegevoegd. Je hebt nu {len(state['sources'])} bron(nen). "
                        "De eerste clips komen na de volgende nachtelijke ronde.")
    elif cmd == "/bronnen":
        lines = [f"{i}. {s}" for i, s in enumerate(state["sources"], 1)]
        tg.send_message("\n".join(lines) or "Nog geen bronnen. Voeg er een toe met /bron <link>")
    elif cmd == "/wisbron" and arg.isdigit() and 1 <= int(arg) <= len(state["sources"]):
        removed = state["sources"].pop(int(arg) - 1)
        tg.send_message(f"Verwijderd: {removed}")
    elif cmd == "/tekst":
        state["campaign_text"] = arg
        tg.send_message("Campagnetekst opgeslagen." if arg else "Campagnetekst leeggemaakt.")
    elif cmd == "/status":
        clips = state["clips"].values()
        pending = sum(1 for c in clips if c["status"] == "pending")
        sched = sorted((c["due"], c["title"]) for c in clips if c["status"] == "scheduled")
        lines = [f"Wacht op jouw keuze: {pending}", f"Bronnen: {len(state['sources'])}", "", "Laatst ingepland:"]
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
