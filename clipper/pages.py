"""Ruimt de map met online clips op: alleen wachtende en pas ingeplande clips blijven staan."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .common import load_state, now_utc


def keep(clip, now):
    if clip["status"] == "pending":
        created = datetime.strptime(clip["created"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return now - created < timedelta(days=4)
    if clip["status"] == "scheduled":
        due = datetime.strptime(clip["due"], "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=timezone.utc)
        return now < due + timedelta(days=2)
    return False


def main(folder):
    state, now = load_state(), now_utc()
    wanted = {c["file"] for c in state["clips"].values() if keep(c, now)}
    for f in Path(folder).glob("*.mp4"):
        if f.name not in wanted:
            f.unlink()
            print("verwijderd:", f.name)
    print(f"{len(list(Path(folder).glob('*.mp4')))} clip(s) online.")


if __name__ == "__main__":
    main(sys.argv[1])
