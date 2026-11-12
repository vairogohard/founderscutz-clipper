"""Lokale test zonder internet: nepvideo + nep-transcript -> momentkeuze -> clip renderen."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from clipper import pick, render  # noqa: E402

work = Path("work/selftest")
work.mkdir(parents=True, exist_ok=True)
src = work / "src.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=44100", "-t", "120",
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(src)], check=True)

script = [
    "So yeah we were just talking about the weather before the show started.",
    "Most founders go broke because they hire too early.",
    "I lost 2 million dollars in one year doing exactly that.",
    "You think more people means more output, but it is the opposite.",
    "Every new hire adds meetings, and meetings kill the work.",
    "The rule I use now is simple.",
    "Never hire until it hurts for at least ninety days.",
    "And that changed everything for the business.",
    "Anyway, it was a nice trip to the lake last summer.",
    "Why do customers leave? It is almost never the price.",
    "They leave because nobody called them back.",
    "We tracked 400 lost accounts and the number one reason was silence.",
    "So we made one habit: call every customer once a month.",
    "Churn dropped by half in six months.",
    "That is the cheapest growth you will ever buy.",
]
words, t = [], 3.0
for si, sentence in enumerate(script):
    for w in sentence.split():
        d = 0.16 + 0.035 * len(w)
        words.append({"start": round(t, 2), "end": round(t + d, 2), "word": w})
        t += d + 0.05
    t += 2.0 if si in (4, 8) else 0.35       # twee lange stiltes om het wegknippen te testen

clips, note = pick.pick_clips(words, 2, min_s=12, max_s=30, models=[])
print("opmerking:", note)
for i, c in enumerate(clips):
    out = work / f"clip{i}.mp4"
    dur = render.render_clip(src, words, c["first"], c["last"], c["title"], out, work / f"w{i}")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,codec_name",
                            "-of", "default=nw=1", str(out)], capture_output=True, text=True).stdout
    print(f"clip{i}: '{c['title']}' start={c['start']:.1f} eind={c['end']:.1f} gepland={dur:.1f}s score={c['score']:.1f}")
    print(probe.replace("\n", " "), out.stat().st_size // 1024, "kB")
