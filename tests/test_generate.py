"""Test de nachtelijke ronde met korte campagnevideo's (download en spraak nagebootst)."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.update(TELEGRAM_BOT_TOKEN="x", TELEGRAM_CHAT_ID="1")
from clipper import campaigns, common, generate, sources, tg, transcribe  # noqa: E402

import tempfile
work = Path(tempfile.mkdtemp())
work.mkdir(parents=True, exist_ok=True)
src = work / "short.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=300", "-t", "90", "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac", str(src)], check=True)

LINES = ["Most people quit right before it starts working.", "I almost shut the whole thing down twice.",
         "Then one video did 4 million views overnight.", "You never know which one will hit.",
         "So the rule is simple, post every single day.", "That is the only secret I have."]
words, t = [], 2.0
for line in LINES * 3:
    for w in line.split():
        words.append({"start": round(t, 2), "end": round(t + 0.32, 2), "word": w})
        t += 0.4
    t += 0.4

VIDEOS = {
    "https://www.youtube.com/watch?v=AAA": {"id": "AAA", "title": "Viral moment one", "duration": 90},
    "https://www.youtube.com/watch?v=BBB": {"id": "BBB", "title": "Viral moment two", "duration": 85},
    "https://www.youtube.com/watch?v=CCC": {"id": "CCC", "title": "Tiny teaser", "duration": 20},
    "https://www.youtube.com/@channel": {"id": "DDD", "title": "Short on a channel", "duration": 120},
}
sources.list_videos = lambda url, limit=8: [dict(VIDEOS[url], url=url)]


def fake_download(video, wd):
    Path(wd).mkdir(parents=True, exist_ok=True)
    shutil.copy(src, Path(wd) / "source.mp4")
    return Path(wd) / "source.mp4", {"title": video["title"]}


sources.download = fake_download
transcribe.transcribe = lambda *a, **k: words
campaigns.ensure_campaign = lambda s, c: False
sent_clips, msgs = [], []
tg.send_clip = lambda path, cap, cid: (sent_clips.append((cid, Path(path).stat().st_size)), {"message_id": len(sent_clips)})[1]
tg.send_message = lambda t: msgs.append(t)

state = dict(common.DEFAULT_STATE, clips={}, processed=[],
             sources=list(VIDEOS))
generate.load_state = lambda: state
generate.save_state = lambda s: None
cfg = common.load_config()
cfg["gemini_models"] = []
generate.load_config = lambda: cfg

assert generate.main() == 0
print("clips:", sent_clips)
print("verwerkt:", state["processed"])
assert len(sent_clips) >= 2, "uit korte video's moeten clips komen"
assert "AAA" in state["processed"] and "BBB" in state["processed"]
assert "DDD" not in state["processed"] and "CCC" not in state["processed"]

# tweede ronde: alles verwerkt of te kort -> bericht met reden
msgs.clear()
generate.main()
print(msgs[-1])
assert "te kort (0:20)" in msgs[-1] and "te kort (2:00)" in msgs[-1]
print("generate-test ok")
