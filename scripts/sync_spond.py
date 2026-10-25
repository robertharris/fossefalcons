"""Pull next fixture and next training sessions per age group from Spond.

Writes data/spond.json. Only whitelisted public fields are written
(title, start/end, location, opponent, home/away) - never member data.
Exits non-zero without touching the file if anything goes wrong.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from spond.spond import Spond

# site key -> exact Spond group name
GROUPS = {
    "u12": "Fosse U12 2026-27",
    "u14": "Fosse U14 2026-27",
    "u16": "Fosse/Trinity/Old Leams U16 2026-27",
}
TRAINING_COUNT = 2
LOOKAHEAD_DAYS = 120
LONDON = ZoneInfo("Europe/London")
OUT = Path(__file__).resolve().parent.parent / "data" / "spond.json"


def parse_ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(LONDON)


def location_of(event):
    loc = event.get("location") or {}
    parts = [loc.get("feature"), loc.get("address")]
    return ", ".join(p for p in parts if p) or None


def simplify(event):
    info = event.get("matchInfo") or {}
    start = parse_ts(event["startTimestamp"])
    end = parse_ts(event["endTimestamp"]) if event.get("endTimestamp") else None
    return {
        "title": event.get("heading"),
        "start": start.isoformat(),
        "end": end.isoformat() if end else None,
        "location": location_of(event),
        "opponent": info.get("opponentName"),
        "home": {"HOME": True, "AWAY": False}.get(info.get("type")),
    }


def is_fixture(event):
    return bool(event.get("matchEvent"))


def is_training(event):
    return not is_fixture(event) and "train" in (event.get("heading") or "").lower()


async def main():
    user, password = os.environ["SPOND_USERNAME"], os.environ["SPOND_PASSWORD"]
    client = Spond(username=user, password=password)
    try:
        groups = {g["name"].strip(): g["id"] for g in await client.get_groups()}
        now = datetime.now(timezone.utc)
        result = {"updated": now.isoformat(timespec="seconds"), "groups": {}}
        for key, name in GROUPS.items():
            if name not in groups:
                raise SystemExit(f"Spond group not found: {name!r}. Found: {sorted(groups)}")
            events = await client.get_events(
                group_id=groups[name],
                min_start=now,
                max_start=now + timedelta(days=LOOKAHEAD_DAYS),
                max_events=100,
            ) or []
            events = [
                e for e in events
                if not e.get("cancelled") and not e.get("hidden") and e.get("startTimestamp")
            ]
            events.sort(key=lambda e: e["startTimestamp"])
            fixtures = [simplify(e) for e in events if is_fixture(e)]
            training = [simplify(e) for e in events if is_training(e)]
            result["groups"][key] = {
                "fixture": fixtures[0] if fixtures else None,
                "training": training[:TRAINING_COUNT],
            }
    finally:
        await client.clientsession.close()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
