"""Een fragment omzetten naar een staande clip (1080x1920) met hooktitel en ondertitels."""
import re
import shutil
import subprocess
from pathlib import Path

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"

LEAD_IN, LEAD_OUT = 0.15, 0.30
MAX_GAP, KEEP_BEFORE, KEEP_AFTER = 0.70, 0.15, 0.20


def plan_segments(words, first, last):
    """Bepaalt welke stukken blijven: lange stiltes tussen woorden worden weggeknipt.

    Geeft (clip_start, segmenten, woorden) terug. Segmenten en woordtijden zijn
    relatief aan clip_start; de woordtijden zijn al gecorrigeerd voor de knips.
    """
    sel = words[first:last + 1]
    cs = max(0.0, sel[0]["start"] - LEAD_IN)
    segments, seg_start = [], 0.0
    for a, b in zip(sel, sel[1:]):
        if b["start"] - a["end"] > MAX_GAP:
            segments.append((seg_start, a["end"] - cs + KEEP_AFTER))
            seg_start = b["start"] - cs - KEEP_BEFORE
    segments.append((seg_start, sel[-1]["end"] - cs + LEAD_OUT))

    def remap(t):
        removed, prev_end = 0.0, 0.0
        for s, e in segments:
            if t >= s:
                removed += s - prev_end
                prev_end = e
        return max(0.0, t - removed)

    out = [{"start": remap(w["start"] - cs), "end": remap(w["end"] - cs), "word": w["word"]} for w in sel]
    return cs, segments, out


def _ts(t):
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def _show(word):
    return _esc(re.sub(r"[.,;:\"]+$", "", word.strip('"')).upper())


def caption_groups(words, max_words=3, max_chars=16):
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        chars = sum(len(x["word"]) for x in cur) + len(cur) - 1
        ends = w["word"].rstrip('"').endswith((".", "?", "!", ","))
        gap = (words[i + 1]["start"] - w["end"]) if i + 1 < len(words) else 99
        nxt = len(words[i + 1]["word"]) if i + 1 < len(words) else 0
        if len(cur) >= max_words or ends or gap > 0.45 or chars + 1 + nxt > max_chars:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def build_ass(words, title, duration, accent="C6FF3D"):
    bgr = accent[4:6] + accent[2:4] + accent[0:2]          # ASS gebruikt BGR
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,Anton,80,&H000C0B0B,&H000C0B0B,&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,1,0,3,14,0,8,90,90,235,1
Style: Cap,Anton,112,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,8,3,2,60,60,395,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [f"Dialogue: 1,{_ts(0)},{_ts(duration)},Hook,,0,0,0,,{_esc(title).upper()}"]
    groups = caption_groups(words)
    for gi, group in enumerate(groups):
        group_end = group[-1]["end"] + 0.25
        if gi + 1 < len(groups):
            group_end = min(group_end, groups[gi + 1][0]["start"])
        for k, w in enumerate(group):
            start = w["start"]
            end = group[k + 1]["start"] if k + 1 < len(group) else group_end
            if end - start < 0.04:
                end = start + 0.04
            parts = []
            for j, x in enumerate(group):
                txt = _show(x["word"])
                parts.append(f"{{\\c&H{bgr}&}}{txt}{{\\c&HFFFFFF&}}" if j == k else txt)
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{' '.join(parts)}")
    return head + "\n".join(lines) + "\n"


def render_clip(src, words, first, last, title, out_path, workdir, accent="C6FF3D"):
    """Rendert de clip en geeft de lengte in seconden terug."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    cs, segments, cwords = plan_segments(words, first, last)
    raw_len = segments[-1][1]
    duration = sum(e - s for s, e in segments)

    (workdir / "subs.ass").write_text(build_ass(cwords, title, duration, accent), encoding="utf-8")
    fonts = workdir / "fonts"
    if not fonts.exists():
        shutil.copytree(FONTS, fonts)

    if len(segments) > 1:
        expr = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in segments)
        vcut = f"select='{expr}',setpts=N/FRAME_RATE/TB,"
        acut = f"aselect='{expr}',asetpts=N/SR/TB,"
    else:
        vcut = acut = ""

    graph = (
        f"[0:v]fps=30,{vcut}split=2[a][b];"
        "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "boxblur=24:2,eq=brightness=-0.22[bg];"
        "[b]crop='min(iw,ih*4/3)':ih,scale=1080:-2[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,ass=subs.ass:fontsdir=fonts,format=yuv420p[v];"
        f"[0:a]{acut}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100[au]"
    )
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{cs:.3f}", "-t", f"{raw_len:.3f}",
           "-i", str(Path(src).resolve()), "-filter_complex", graph, "-map", "[v]", "-map", "[au]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-maxrate", "3500k",
           "-bufsize", "7000k", "-profile:v", "high", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
           str(Path(out_path).resolve())]
    subprocess.run(cmd, check=True, cwd=workdir)
    return duration
