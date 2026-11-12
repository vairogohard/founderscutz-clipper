"""Telegram-bot: clips ter goedkeuring sturen en antwoorden uitlezen."""
import json

import requests

from .common import env

API = "https://api.telegram.org/bot{token}/{method}"


def _call(method, data=None, files=None, timeout=120):
    url = API.format(token=env("TELEGRAM_BOT_TOKEN"), method=method)
    r = requests.post(url, data=data or {}, files=files, timeout=timeout)
    try:
        body = r.json()
    except ValueError:
        raise RuntimeError(f"Telegram gaf geen geldig antwoord ({r.status_code}).")
    if not body.get("ok"):
        raise RuntimeError(f"Telegram-fout bij {method}: {body.get('description')}")
    return body["result"]


def chat_id():
    return env("TELEGRAM_CHAT_ID")


def send_message(text):
    return _call("sendMessage", {"chat_id": chat_id(), "text": text[:4000], "disable_web_page_preview": "true"})


def send_clip(path, caption, clip_id):
    keyboard = {"inline_keyboard": [[
        {"text": "✅ Plaatsen", "callback_data": f"ok:{clip_id}"},
        {"text": "❌ Weggooien", "callback_data": f"no:{clip_id}"},
    ]]}
    with open(path, "rb") as f:
        return _call(
            "sendVideo",
            {"chat_id": chat_id(), "caption": caption[:1000], "supports_streaming": "true",
             "reply_markup": json.dumps(keyboard)},
            files={"video": (f"{clip_id}.mp4", f, "video/mp4")},
            timeout=600,
        )


def get_updates(offset):
    return _call("getUpdates", {"offset": offset, "timeout": 0,
                                "allowed_updates": json.dumps(["message", "callback_query"])})


def answer_callback(callback_id, text=""):
    try:
        _call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:190]})
    except RuntimeError:
        pass  # de tik is te oud om te beantwoorden; niet erg


def edit_caption(message_id, caption):
    """Vervangt het bijschrift en haalt de knoppen weg."""
    try:
        _call("editMessageCaption", {"chat_id": chat_id(), "message_id": message_id,
                                     "caption": caption[:1000],
                                     "reply_markup": json.dumps({"inline_keyboard": []})})
    except RuntimeError as e:
        print("Kon bericht niet aanpassen:", e)
