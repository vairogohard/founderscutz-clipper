"""Gedeelde hulpfuncties: instellingen, status (state) en tijd."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "state" / "state.json"
CONFIG_FILE = ROOT / "config.yml"

DEFAULT_STATE = {"tg_offset": 0, "processed": [], "sources": [], "campaign_text": "", "clips": {}}


def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.setdefault("timezone", "Europe/Amsterdam")
    cfg.setdefault("clips_per_day", 4)
    cfg.setdefault("post_times", ["12:00", "17:00", "20:00"])
    cfg.setdefault("clip_seconds", {"min": 20, "max": 45})
    cfg.setdefault("max_source_minutes", 75)
    cfg.setdefault("whisper_model", "base.en")
    cfg.setdefault("caption_suffix", "")
    cfg.setdefault("youtube_category", "22")
    cfg.setdefault("gemini_models", ["gemini-flash-latest"])
    cfg.setdefault("accent_color", "C6FF3D")
    cfg.setdefault("channels", [])
    return cfg


def load_state():
    state = dict(DEFAULT_STATE)
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            state.update(json.load(f))
    return state


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")


def env(name, required=True):
    value = os.environ.get(name, "").strip()
    if required and not value:
        raise SystemExit(f"Omgevingsvariabele {name} ontbreekt (GitHub-secret niet ingesteld?).")
    return value


def now_utc():
    return datetime.now(timezone.utc)


def pages_base_url():
    """Publiek adres van de clips op GitHub Pages."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in repo:
        return os.environ.get("PAGES_BASE_URL", "")
    owner, name = repo.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}"


def next_slot(state, cfg, now=None, min_lead_minutes=25):
    """Eerstvolgende vrije plaatsingstijd (UTC), minstens min_lead_minutes vooruit."""
    tz = ZoneInfo(cfg["timezone"])
    now = now or now_utc()
    taken = {c.get("due") for c in state["clips"].values() if c.get("status") == "scheduled"}
    earliest = now + timedelta(minutes=min_lead_minutes)
    day = now.astimezone(tz).date()
    for offset in range(0, 30):
        d = day + timedelta(days=offset)
        for hhmm in sorted(cfg["post_times"]):
            h, m = [int(x) for x in hhmm.split(":")]
            local = datetime(d.year, d.month, d.day, h, m, tzinfo=tz)
            utc = local.astimezone(timezone.utc)
            iso = utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            if utc >= earliest and iso not in taken:
                return iso
    raise RuntimeError("Geen vrije plaatsingstijd gevonden in de komende 30 dagen.")


DAGEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]
MAANDEN = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]


def fmt_local(iso, cfg):
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=timezone.utc)
    loc = dt.astimezone(ZoneInfo(cfg["timezone"]))
    return f"{DAGEN[loc.weekday()]} {loc.day} {MAANDEN[loc.month - 1]} {loc:%H:%M}"
