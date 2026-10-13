"""Record real NHL API responses into tests/fixtures/real/ for parser tests.

Run on a machine that can reach api-web.nhle.com:
    python scripts/record_fixtures.py --team BOS --game 2024020500
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

BASE = "https://api-web.nhle.com/v1"
OUT = Path(__file__).parent.parent / "tests" / "fixtures" / "real"


def fetch(path: str) -> dict:
    req = Request(f"{BASE}/{path}", headers={"User-Agent": "nhl-companion-fixture-recorder"})
    with urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--team", default="BOS")
    parser.add_argument("--game", type=int, action="append", default=[], help="Game id(s) for play-by-play")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    targets = {
        "schedule_now.json": "schedule/now",
        "standings_now.json": "standings/now",
        f"club_schedule_{args.team}.json": f"club-schedule-season/{args.team}/now",
    }
    for gid in args.game:
        targets[f"pbp_{gid}.json"] = f"gamecenter/{gid}/play-by-play"
    for name, path in targets.items():
        data = fetch(path)
        (OUT / name).write_text(json.dumps(data, indent=1))
        print(f"wrote {OUT / name}")


if __name__ == "__main__":
    main()
