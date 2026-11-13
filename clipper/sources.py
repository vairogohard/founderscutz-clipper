"""Bronvideo's vinden en downloaden (alleen materiaal van je campagne)."""
import os
from pathlib import Path

import yt_dlp

COOKIE_HINTS = ("sign in to confirm", "not a bot", "cookies", "login required")


def base_opts():
    """Gedeelde instellingen: YouTube-cookies (GitHub-secret YT_COOKIES) als die er zijn."""
    opts = {"quiet": True, "no_warnings": False}
    cookie_file = os.environ.get("YTDLP_COOKIES", "")
    if cookie_file and Path(cookie_file).exists():
        opts["cookiefile"] = cookie_file
    return opts


def is_cookie_error(text):
    return any(h in str(text).lower() for h in COOKIE_HINTS)


def _normalize(url):
    url = url.strip()
    # Kanaal-link zonder tabblad -> het tabblad met lange video's.
    if ("youtube.com/@" in url or "youtube.com/channel/" in url or "youtube.com/c/" in url) \
            and not url.rstrip("/").endswith(("/videos", "/streams", "/podcasts")):
        url = url.rstrip("/") + "/videos"
    return url


def list_videos(url, limit=8):
    """Nieuwste video's van een kanaal, playlist of losse video."""
    opts = dict(base_opts(), extract_flat=True, playlistend=limit, skip_download=True)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(_normalize(url), download=False)
    entries = info.get("entries")
    if entries is None:
        entries = [info]
    videos = []
    for e in entries:
        if not e or not e.get("id"):
            continue
        videos.append({
            "id": e["id"],
            "title": e.get("title") or "",
            "url": e.get("url") or e.get("webpage_url") or f"https://www.youtube.com/watch?v={e['id']}",
            "duration": e.get("duration"),
        })
    return videos


SINGLE_VIDEO = ("youtube.com/watch", "youtu.be/", "drive.google.com/file/")


def pick_new_video(sources, processed, min_minutes=6, single_min_seconds=45):
    """Eerste nog niet verwerkte video uit de bronnen.

    Bij een kanaal of playlist slaan we korte video's over (dat zijn vaak Shorts). Een losse video
    die de campagne zelf aanwijst, mag kort zijn. Overgeslagen video's komen met reden in de lijst."""
    errors = []
    for src in sources:
        single = any(x in src for x in SINGLE_VIDEO)
        limit = single_min_seconds if single else min_minutes * 60
        try:
            for v in list_videos(src):
                if v["id"] in processed:
                    continue
                if v["duration"] is not None and v["duration"] < limit:
                    d = int(v["duration"])
                    errors.append(f"overgeslagen, te kort ({d // 60}:{d % 60:02d}): {v['title'][:50] or v['id']}")
                    continue
                return v, errors
        except Exception as e:  # noqa: BLE001 - we willen door naar de volgende bron
            errors.append(f"{src}: {str(e)[:200]}")
    return None, errors


def download(video, workdir):
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    out = workdir / "source.mp4"
    opts = {
        **base_opts(),
        "noprogress": True,
        "outtmpl": str(workdir / "source.%(ext)s"),
        "format": "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b[height<=720]/b",
        "merge_output_format": "mp4",
        "retries": 3,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video["url"], download=True)
    if not out.exists():
        found = sorted(workdir.glob("source.*"))
        if not found:
            raise RuntimeError("Download mislukt: geen bestand gevonden.")
        out = found[0]
    return out, {"title": info.get("title") or video.get("title", ""),
                 "uploader": info.get("uploader") or info.get("channel") or "",
                 "duration": info.get("duration")}
