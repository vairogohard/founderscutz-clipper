"""Bronvideo's vinden en downloaden (alleen materiaal van je campagne)."""
from pathlib import Path

import yt_dlp


def _normalize(url):
    url = url.strip()
    # Kanaal-link zonder tabblad -> het tabblad met lange video's.
    if ("youtube.com/@" in url or "youtube.com/channel/" in url or "youtube.com/c/" in url) \
            and not url.rstrip("/").endswith(("/videos", "/streams", "/podcasts")):
        url = url.rstrip("/") + "/videos"
    return url


def list_videos(url, limit=8):
    """Nieuwste video's van een kanaal, playlist of losse video."""
    opts = {"quiet": True, "extract_flat": True, "playlistend": limit, "skip_download": True}
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


def pick_new_video(sources, processed, min_minutes=6):
    """Eerste nog niet verwerkte lange video uit de bronnen."""
    errors = []
    for src in sources:
        try:
            for v in list_videos(src):
                if v["id"] in processed:
                    continue
                if v["duration"] is not None and v["duration"] < min_minutes * 60:
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
        "quiet": True,
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
