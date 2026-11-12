"""Test de goedkeuringslogica met nagebootste Telegram- en Buffer-antwoorden (geen internet nodig)."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.update(TELEGRAM_BOT_TOKEN="x", TELEGRAM_CHAT_ID="111", BUFFER_API_KEY="x",
                  GITHUB_REPOSITORY="Vairo/founderscutz-clipper")
from clipper import buffer_api, common, poll, tg  # noqa: E402

state = {"tg_offset": 0, "processed": [], "sources": [], "campaign_text": "", "clips": {
    "a": {"status": "pending", "title": "Why founders go broke", "caption": "The hiring trap.",
          "file": "a.mp4", "message_id": 1, "created": "2026-11-12T03:00:00Z"},
    "b": {"status": "pending", "title": "Second", "caption": "", "file": "b.mp4", "message_id": 2,
          "created": "2026-11-12T03:00:00Z"},
    "c": {"status": "pending", "title": "Third", "caption": "", "file": "c.mp4", "message_id": 3,
          "created": "2026-11-12T03:00:00Z"}}}
cfg = common.load_config()
cfg["channels"] = [{"id": "yt1", "service": "youtube"}, {"id": "ig1", "service": "instagram"}]

sent, queries, edits = [], [], []
updates = [
    {"update_id": 5, "callback_query": {"id": "q1", "from": {"id": 111}, "data": "ok:a"}},
    {"update_id": 6, "callback_query": {"id": "q2", "from": {"id": 111}, "data": "no:b"}},
    {"update_id": 7, "callback_query": {"id": "q3", "from": {"id": 999}, "data": "ok:c"}},   # vreemde: negeren
    {"update_id": 8, "message": {"chat": {"id": 111}, "text": "/bron https://youtube.com/@somepodcast"}},
    {"update_id": 9, "message": {"chat": {"id": 111}, "text": "/tekst #ad @brand"}},
    {"update_id": 10, "callback_query": {"id": "q4", "from": {"id": 111}, "data": "ok:c"}},
    {"update_id": 11, "message": {"chat": {"id": 111}, "text": "/status"}},
]
tg.get_updates = lambda offset: updates
tg.send_message = lambda text: sent.append(text)
tg.answer_callback = lambda *a, **k: None
tg.edit_caption = lambda mid, cap: edits.append((mid, cap))
poll.is_online = lambda url: True
common.load_state = poll.load_state = lambda: state
poll.load_config = lambda: cfg
poll.save_state = lambda s: None

def fake_gql(query):
    queries.append(query)
    return {"createPost": {"post": {"id": f"p{len(queries)}", "dueAt": "x"}}}
buffer_api.gql = fake_gql

poll.main()
assert state["clips"]["a"]["status"] == "scheduled" and state["clips"]["b"]["status"] == "rejected"
assert state["clips"]["c"]["status"] == "scheduled"
assert state["clips"]["a"]["due"] != state["clips"]["c"]["due"], "twee clips op hetzelfde tijdstip"
assert state["sources"] == ["https://youtube.com/@somepodcast"] and state["campaign_text"] == "#ad @brand"
assert state["tg_offset"] == 12 and len(queries) == 4
print(queries[0])
print(queries[3])
print("bijschriften:", edits)
print("berichten:", sent)
# vaste tijd: donderdag 12 nov 2026 22:50 NL -> eerstvolgende slot vrijdag 12:00 NL = 11:00 UTC
slot = common.next_slot({"clips": {}}, cfg, datetime(2026, 11, 12, 21, 50, tzinfo=timezone.utc))
assert slot == "2026-11-13T11:00:00.000Z", slot
print("slot ok:", slot, "->", common.fmt_local(slot, cfg))
