"""Trim a record_live.py recording into a small replay fixture for the test suite.

Usage (from the repo root, with Home Assistant installed in the venv):
    python scripts/trim_recording.py <recording dir> --team STL --out tests/fixtures/replay/<name>.json.gz

Keeps the first and last snapshot, every snapshot where the event detector fires
or a tracked play is added, edited or removed, and the one before each. Plays are
cut to those that are a goal, penalty, delayed penalty or period/game marker in
any snapshot, so a shot that later turns into a goal is kept. The roster is
stored once.
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from custom_components.nhl_companion.event_detector import EventDetector
from custom_components.nhl_companion.parser import parse_play_by_play

# Fields the detector reads; a change in any of these keeps the snapshot
WATCHED_DETAILS = (
    "scoringPlayerId",
    "assist1PlayerId",
    "assist2PlayerId",
    "committedByPlayerId",
    "drawnByPlayerId",
    "descKey",
    "duration",
    "typeCode",
    "discreteClip",
    "highlightClip",
)
# Not used by the integration; dropped to keep the fixture small
DROP_ROOT = ("tvBroadcasts", "summary", "venueLocation")
DROP_PLAY = ("pptReplayUrl", "homeTeamDefendingSide")

KEEP_TYPES = {
    "goal",
    "penalty",
    "delayed-penalty",
    "period-start",
    "period-end",
    "game-end",
    "shootout-complete",
}


def _slim(play: dict) -> dict:
    play = {k: v for k, v in play.items() if k not in DROP_PLAY}
    if details := play.get("details"):
        play["details"] = {k: v for k, v in details.items() if not k.endswith("Fr")}
    return play


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("recording", type=Path)
    ap.add_argument("--team", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    paths = sorted((args.recording / "snapshots").glob("*.json"))
    raws = [json.loads(p.read_text()) for p in paths]

    tracked = {
        p["eventId"] for raw in raws for p in raw.get("plays", []) if p.get("typeDescKey") in KEEP_TYPES
    }

    def signature(raw: dict) -> str:
        plays = [
            (p["eventId"], p.get("typeDescKey"), [(p.get("details") or {}).get(k) for k in WATCHED_DETAILS])
            for p in raw.get("plays", [])
            if p.get("eventId") in tracked
        ]
        state = (raw.get("gameState"), raw.get("clock", {}).get("inIntermission"))
        return json.dumps([state, sorted(plays)])

    detector = EventDetector(args.team)
    keep = {0, len(raws) - 1}
    previous = None
    for i, raw in enumerate(raws):
        sig = signature(raw)
        if detector.process(parse_play_by_play(raw)) or (previous is not None and sig != previous):
            keep.update({max(i - 1, 0), i})
        previous = sig
    roster: dict[int, dict] = {}
    snapshots = []
    for i in sorted(keep):
        raw = dict(raws[i])
        for spot in raw.pop("rosterSpots", []):
            roster[spot["playerId"]] = spot
        for key in DROP_ROOT:
            raw.pop(key, None)
        raw["plays"] = [_slim(p) for p in raw.get("plays", []) if p.get("eventId") in tracked]
        raw["recorded_as"] = paths[i].name
        snapshots.append(raw)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"team": args.team, "rosterSpots": list(roster.values()), "snapshots": snapshots})
    with gzip.open(args.out, "wt", encoding="utf-8") as fh:
        fh.write(payload)
    print(f"{len(snapshots)} of {len(raws)} snapshots, {args.out.stat().st_size // 1024} KB -> {args.out}")


if __name__ == "__main__":
    main()
