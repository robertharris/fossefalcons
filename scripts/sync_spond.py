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

# Exact Spond group IDs for the age groups. These are set on the account that
# owns the groups; the script fetches events from each group directly.
GROUPS = {
    "u12": "B60AE301C9BF4DC8A105BAC936F4AC44",
    "u14": "8719540A5B0D4DADB0AACBC576B21E5C",
    "u16": "9E23AD45217E49D0BAC7AE55B1263E86",
}
TRAINING_COUNT = 2
LOOKAHEAD_DAYS = 120
DEBUG = "--debug" in sys.argv
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
    if is_fixture(event):
        return False
    heading = (event.get("heading") or "").lower()
    if not heading:
        return False
    excluded = (
        "team building",
        "committee",
        "social",
        "meeting",
        "women’s match",
        "women's match",
    )
    if any(item in heading for item in excluded):
        return False
    return any(item in heading for item in ("training", "train"))


async def main():
    user, password = os.environ["SPOND_USERNAME"], os.environ["SPOND_PASSWORD"]
    client = Spond(username=user, password=password)
    try:
        if DEBUG:
            all_groups = await client.get_groups() or []
            print("---- Spond groups on this account ----")
            for g in all_groups:
                print("GROUP", repr(g.get("name")), g.get("id"))
                for sg in g.get("subGroups", []) or []:
                    print("  SUBGROUP", repr(sg.get("name")), sg.get("id"))
        now = datetime.now(timezone.utc)
        result = {"updated": now.isoformat(timespec="seconds"), "groups": {}}
        for key, group_id in GROUPS.items():
            # Some Spond events are created ahead of time as scheduled/hidden items.
            # Pull those too so the website can show upcoming fixtures as soon as they appear.
            events = await client.get_events(
                group_id=group_id,
                include_scheduled=True,
                include_hidden=True,
                min_start=now,
                max_start=now + timedelta(days=LOOKAHEAD_DAYS),
                max_events=100,
            ) or []
            if DEBUG:
                print(f"== {key} group_id={group_id}: {len(events)} events")
                for i, e in enumerate(events[:5], 1):
                    print("  event", i, "keys=", sorted(e.keys())[:15])
                    print("  ", e.get("startTimestamp"), repr(e.get("heading")), "match=", e.get("matchEvent"),
                          "cancelled=", e.get("cancelled"), "hidden=", e.get("hidden"))
                    if i == 5:
                        break
            # Some Spond groups keep upcoming fixtures/meetings as hidden events, even
            # though they are valid and should still be displayed on the website.
            events = [
                e for e in events
                if not e.get("cancelled") and e.get("startTimestamp")
                and parse_ts(e["startTimestamp"]) >= now
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
    for key, payload in result["groups"].items():
        fixture = payload.get("fixture")
        training = payload.get("training") or []
        if fixture:
            start = parse_ts(fixture["start"]).strftime("%a %d %b %H:%M")
            opp = fixture.get("opponent") or "opponent"
            print(f"{key}: next fixture = {start} vs {opp}")
        else:
            print(f"{key}: next fixture = none")
        if training:
            for idx, event in enumerate(training, 1):
                start = parse_ts(event["start"]).strftime("%a %d %b %H:%M")
                print(f"{key}: training {idx} = {start} {event.get('title') or 'Training'}")
        else:
            print(f"{key}: training = none")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
