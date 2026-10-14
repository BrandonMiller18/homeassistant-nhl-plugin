"""Trim a record_live.py recording into a small replay fixture for the test suite.

Usage (from the repo root, with Home Assistant installed in the venv):
    python scripts/trim_recording.py <recording dir> --team STL --out tests/fixtures/replay/<name>.json

Keeps the first and last snapshot, every snapshot where the event detector fires,
and the one before each. Plays are cut to those that are a goal, penalty, delayed
penalty or period/game marker in any snapshot, so a shot that later turns into a
goal is kept. The roster is stored once.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from custom_components.nhl_companion.event_detector import EventDetector
from custom_components.nhl_companion.parser import parse_play_by_play

KEEP_TYPES = {
    "goal",
    "penalty",
    "delayed-penalty",
    "period-start",
    "period-end",
    "game-end",
    "shootout-complete",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("recording", type=Path)
    ap.add_argument("--team", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    paths = sorted((args.recording / "snapshots").glob("*.json"))
    raws = [json.loads(p.read_text()) for p in paths]

    detector = EventDetector(args.team)
    fired = [bool(detector.process(parse_play_by_play(raw))) for raw in raws]
    keep = {0, len(raws) - 1}
    for i, hit in enumerate(fired):
        if hit:
            keep.update({i - 1, i})

    tracked = {
        p["eventId"] for raw in raws for p in raw.get("plays", []) if p.get("typeDescKey") in KEEP_TYPES
    }
    roster: dict[int, dict] = {}
    snapshots = []
    for i in sorted(keep):
        raw = dict(raws[i])
        for spot in raw.pop("rosterSpots", []):
            roster[spot["playerId"]] = spot
        raw["plays"] = [p for p in raw.get("plays", []) if p.get("eventId") in tracked]
        raw["recorded_as"] = paths[i].name
        snapshots.append(raw)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"team": args.team, "rosterSpots": list(roster.values()), "snapshots": snapshots})
    )
    print(f"{len(snapshots)} of {len(raws)} snapshots, {args.out.stat().st_size // 1024} KB -> {args.out}")


if __name__ == "__main__":
    main()
