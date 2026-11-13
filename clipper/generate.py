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

    n = int(cfg["clips_per_day"])
    sent_total, notes, tried = 0, [], 0
    errors = []
    while sent_total < n and tried < 6:
        video, errors = sources.pick_new_video(srcs, set(state["processed"]))
        if video is None:
            break
        tried += 1
        sent, note = process_video(video, n - sent_total, cfg, state)
        sent_total += sent
        if note:
            notes.append(note)
        state["processed"].append(video["id"])
        state["processed"] = state["processed"][-500:]
        save_state(state)

    if sent_total:
        for note in dict.fromkeys(notes):
            tg.send_message(note)
        return 0
    if errors and all(sources.is_cookie_error(e) for e in errors):
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
    msg = ("Ik heb video's verwerkt maar er kwamen geen bruikbare clips uit." if tried else
           "Geen nieuwe video gevonden bij je bronnen, dus vandaag geen nieuwe clips.")
    if errors:
        msg += "\n\nDetails:\n" + "\n".join(errors[:12])
    tg.send_message(msg)
    return 0


def process_video(video, want, cfg, state):
    """Eén bronvideo downloaden en er maximaal `want` clips uit naar Telegram sturen.
    Geeft (aantal verstuurd, opmerking) terug."""
    shutil.rmtree(WORK, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    print("Video:", video["title"], video["url"])
    try:
        src, info = sources.download(video, WORK)
    except Exception as e:  # noqa: BLE001
        return 0, f"Downloaden van '{video['title'][:60]}' mislukt: {str(e)[:250]}"
    words = transcribe.transcribe(src, WORK, cfg["whisper_model"], cfg["max_source_minutes"])
    if len(words) < 50:
        return 0, f"Te weinig spraak in '{info['title'][:60]}', overgeslagen."

    clips, note = pick.pick_clips(words, want, cfg["clip_seconds"]["min"], cfg["clip_seconds"]["max"],
                                  cfg["gemini_models"])
    if not clips:
        return 0, None

    stamp = datetime.now().strftime("%y%m%d")
    sent = 0
    for i, c in enumerate(clips, 1):
        clip_id = f"{stamp}-{video['id'][:8]}-{i}"
        out = OUT / f"{clip_id}.mp4"
        try:
            dur = render.render_clip(src, words, c["first"], c["last"], c["title"], out,
                                     WORK / f"clip{i}", cfg["accent_color"])
            caption = (f"{c['title']}\n"
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
    return sent, note

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
