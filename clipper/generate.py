"""Nachtelijke taak: nieuwe bronvideo ophalen, clips maken en ter controle naar Telegram sturen."""
import os
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

from . import campaigns, pick, render, sources, tg, transcribe
from .common import ROOT, load_config, load_state, now_utc, save_state

WORK = ROOT / "work"
OUT = ROOT / "out" / "clips"


def main():
    cfg, state = load_config(), load_state()
    try:
        if campaigns.ensure_campaign(state, cfg):
            save_state(state)
    except Exception:  # noqa: BLE001 - zonder nieuwe campagne gaan we gewoon door
        traceback.print_exc()
    srcs = state.get("sources") or []
    if not srcs:
        tg.send_message("Er is nog geen bron voor de clips. Stuur mij: /bron <link naar het kanaal, "
                        "de playlist of de video van je campagne>")
        return 0

    video, errors = sources.pick_new_video(srcs, set(state["processed"]))
    if video is None and errors and all(sources.is_cookie_error(e) for e in errors):
        has = bool(os.environ.get("YTDLP_COOKIES"))
        tg.send_message(
            ("YouTube weigert de download: je YouTube-cookies zijn verlopen." if has else
             "YouTube weigert downloads vanaf GitHub zonder YouTube-cookies.") +
            "\n\nVernieuwen (2 minuten):\n"
            "1. Open Chrome in een incognitovenster en log in op YouTube met je losse Google-account.\n"
            "2. Ga in hetzelfde tabblad naar youtube.com/robots.txt.\n"
            "3. Exporteer de cookies met 'Get cookies.txt LOCALLY' en sluit het incognitovenster meteen.\n"
            "4. Typ in de VS Code-terminal van je clipper: bash tools/cookies.sh en sleep het cookiebestand erin.")
        return 0
    if video is None:
        msg = "Geen nieuwe video gevonden bij je bronnen, dus vandaag geen nieuwe clips."
        if errors:
            msg += "\n\nFouten bij het ophalen:\n" + "\n".join(errors)
        tg.send_message(msg)
        return 0

    shutil.rmtree(WORK, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    print("Video:", video["title"], video["url"])
    src, info = sources.download(video, WORK)
    words = transcribe.transcribe(src, WORK, cfg["whisper_model"], cfg["max_source_minutes"])
    if len(words) < 150:
        state["processed"].append(video["id"])
        save_state(state)
        tg.send_message(f"Te weinig spraak gevonden in '{info['title']}', overgeslagen.")
        return 0

    n = int(cfg["clips_per_day"])
    clips, note = pick.pick_clips(words, n, cfg["clip_seconds"]["min"], cfg["clip_seconds"]["max"],
                                  cfg["gemini_models"])
    if not clips:
        state["processed"].append(video["id"])
        save_state(state)
        tg.send_message(f"Geen geschikte momenten gevonden in '{info['title']}'.")
        return 0

    stamp = datetime.now().strftime("%y%m%d")
    sent = 0
    for i, c in enumerate(clips, 1):
        clip_id = f"{stamp}-{video['id'][:8]}-{i}"
        out = OUT / f"{clip_id}.mp4"
        try:
            dur = render.render_clip(src, words, c["first"], c["last"], c["title"], out,
                                     WORK / f"clip{i}", cfg["accent_color"])
            caption = (f"{i}/{len(clips)}  {c['title']}\n"
                       f"{dur:.0f} sec, uit: {info['title'][:80]}\n\n"
                       "Tik op Plaatsen of Weggooien.")
            message = tg.send_clip(out, caption, clip_id)
        except Exception as e:  # noqa: BLE001 - één mislukte clip mag de rest niet tegenhouden
            print("Clip mislukt:", e)
            traceback.print_exc()
            out.unlink(missing_ok=True)
            continue
        state["clips"][clip_id] = {
            "status": "pending", "title": c["title"], "caption": c.get("caption", ""),
            "file": out.name, "message_id": message["message_id"],
            "source_title": info["title"], "source_url": video["url"],
            "created": now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        sent += 1
        save_state(state)

    state["processed"].append(video["id"])
    state["processed"] = state["processed"][-500:]
    save_state(state)
    if sent == 0:
        tg.send_message(f"Het maken van de clips uit '{info['title']}' is mislukt. Kijk in GitHub "
                        "onder Actions voor de foutmelding.")
        return 1
    if note:
        tg.send_message(note)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        try:
            tg.send_message(f"De clipper liep vast: {str(e)[:500]}\n\nKijk in GitHub onder Actions "
                            "voor de volledige foutmelding.")
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)
