"""Test de nachtelijke ronde: korte campagnevideo's (in hun geheel) en een langere (knippen)."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.update(TELEGRAM_BOT_TOKEN="x", TELEGRAM_CHAT_ID="1")
from clipper import campaigns, common, generate, sources, tg, transcribe  # noqa: E402

work = Path(tempfile.mkdtemp())
long_src, short_src = work / "long.mp4", work / "short.mp4"
for path, size, secs in ((long_src, "1280x720", 90), (short_src, "1080x1920", 8)):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=300", "-t", str(secs), "-c:v", "libx264",
                    "-preset", "ultrafast", "-c:a", "aac", str(path)], check=True)

LINES = ["Most people quit right before it starts working.", "I almost shut the whole thing down twice.",
         "Then one video did 4 million views overnight.", "You never know which one will hit.",
         "So the rule is simple, post every single day.", "That is the only secret I have."]
long_words, t = [], 2.0
for line in LINES * 3:
    for w in line.split():
        long_words.append({"start": round(t, 2), "end": round(t + 0.32, 2), "word": w})
        t += 0.4
    t += 0.4
short_words = [{"start": 1.0 + 0.4 * i, "end": 1.3 + 0.4 * i, "word": w}
               for i, w in enumerate("bro really tried to impress her like that".split())]

W = "https://www.youtube.com/watch?v="
VIDEOS = {
    W + "S1": {"id": "S1", "title": "When You Start Treating Them How They Treat You🤡😭W", "duration": 8},
    W + "S2": {"id": "S2", "title": "Michaela Crashes Out On K-Shiday For Stealing Her", "duration": 23},
    W + "S3": {"id": "S3", "title": "Too tiny", "duration": 3},
    W + "AAA": {"id": "AAA", "title": "Longer viral moment", "duration": 90},
    "https://www.youtube.com/@channel": {"id": "DDD", "title": "Short on a channel", "duration": 40},
}
sources.list_videos = lambda url, limit=8: [dict(VIDEOS[url], url=url)]


def fake_download(video, wd):
    Path(wd).mkdir(parents=True, exist_ok=True)
    shutil.copy(long_src if video["id"] == "AAA" else short_src, Path(wd) / "source.mp4")
    return Path(wd) / "source.mp4", {"title": video["title"]}


sources.download = fake_download
transcribe.transcribe = lambda path, *a, **k: long_words if "AAA" in str(CURRENT[0]) else short_words
CURRENT = [""]
orig_pick = sources.pick_new_video


def tracking_pick(srcs, done):
    v, e = orig_pick(srcs, done)
    CURRENT[0] = v["id"] if v else ""
    return v, e


sources.pick_new_video = tracking_pick
campaigns.ensure_campaign = lambda s, c: False
sent_clips, msgs = [], []
KEEP = work / "kept"
KEEP.mkdir()


def fake_send(path, cap, cid):
    shutil.copy(path, KEEP / f"{cid}.mp4")
    sent_clips.append((cid, cap.splitlines()[0]))
    return {"message_id": len(sent_clips)}


tg.send_clip = fake_send
tg.send_message = lambda t: msgs.append(t)
state = dict(common.DEFAULT_STATE, clips={}, processed=[], sources=list(VIDEOS))
generate.load_state = lambda: state
generate.save_state = lambda s: None
cfg = dict(common.load_config(), gemini_models=[])
generate.load_config = lambda: cfg

assert generate.main() == 0
for c in sent_clips:
    print("clip:", c)
assert [c[0].split("-")[1] for c in sent_clips] == ["S1", "S2", "AAA", "AAA"], sent_clips
assert sent_clips[0][1] == "When You Start Treating Them How They Treat You"
assert "S3" not in state["processed"] and "DDD" not in state["processed"]
print("bewaard in", KEEP)
print("generate-test ok")
