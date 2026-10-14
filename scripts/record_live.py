"""Record a live NHL game and run it through the integration's real parser and detector.

Usage (from the repo root, with Home Assistant installed in the venv):
    python scripts/record_live.py --team STL --out /tmp/live_stl

Every poll saves the play-by-play JSON when it changes, logs response headers and
timing, reports plays whose details were edited after first appearing, and prints
every event the integration would fire. Stops a while after the game goes final.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

import aiohttp

sys.path.insert(0, str(Path(__file__).parent.parent))
from custom_components.nhl_companion.event_detector import EventDetector
from custom_components.nhl_companion.parser import parse_play_by_play

BASE = "https://api-web.nhle.com/v1"
HEADERS_OF_INTEREST = (
    "cache-control",
    "age",
    "etag",
    "last-modified",
    "date",
    "expires",
    "x-cache",
    "cf-cache-status",
)
TRACKED_TYPES = {
    "goal",
    "penalty",
    "period-start",
    "period-end",
    "game-end",
    "shootout-complete",
    "delayed-penalty",
}


def now() -> str:
    return datetime.now(UTC).strftime("%H:%M:%S")


def say(kind: str, msg: str) -> None:
    print(f"{now()} {kind} {msg}", flush=True)


async def fetch(session: aiohttp.ClientSession, path: str, headers: dict[str, str] | None = None):
    start = time.monotonic()
    async with session.get(
        f"{BASE}/{path}", headers=headers or {}, timeout=aiohttp.ClientTimeout(total=20)
    ) as resp:
        body = await resp.read()
        meta = {
            "status": resp.status,
            "ms": round((time.monotonic() - start) * 1000),
            "bytes": len(body),
            "url": str(resp.url),
            **{h: resp.headers.get(h) for h in HEADERS_OF_INTEREST if resp.headers.get(h)},
        }
        return meta, body


async def find_game(session: aiohttp.ClientSession, team: str) -> int | None:
    _meta, body = await fetch(session, "score/now")
    data = json.loads(body)
    for game in data.get("games", []):
        abbrevs = {game.get("homeTeam", {}).get("abbrev"), game.get("awayTeam", {}).get("abbrev")}
        if team in abbrevs:
            say(
                "INFO",
                f"found game {game['id']} {game['awayTeam']['abbrev']}@{game['homeTeam']['abbrev']} state={game.get('gameState')}",
            )
            return int(game["id"])
    return None


def describe(play: dict[str, Any]) -> str:
    d = play.get("details") or {}
    keys = {
        k: v
        for k, v in d.items()
        if k.endswith("PlayerId") or k in ("descKey", "duration", "typeCode", "homeScore", "awayScore")
    }
    return f"{play.get('typeDescKey')} p{play.get('periodDescriptor', {}).get('number')} {play.get('timeInPeriod')} sit={play.get('situationCode')} {keys}"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", default="STL")
    ap.add_argument("--game", type=int)
    ap.add_argument("--interval", type=float, default=10)
    ap.add_argument("--out", default="live_recording")
    ap.add_argument("--after-final", type=int, default=600, help="Seconds to keep polling after FINAL/OFF")
    args = ap.parse_args()
    out = Path(args.out)
    (out / "snapshots").mkdir(parents=True, exist_ok=True)
    polls = (out / "polls.jsonl").open("a")
    events_log = (out / "events.jsonl").open("a")

    async with aiohttp.ClientSession(headers={"User-Agent": "nhl-companion-live-recorder"}) as session:
        game_id = args.game or await find_game(session, args.team)
        if not game_id:
            say("ERROR", f"no {args.team} game in /score/now")
            return
        for path in (
            "score/now",
            f"gamecenter/{game_id}/landing",
            f"gamecenter/{game_id}/boxscore",
            "standings/now",
            f"club-schedule-season/{args.team}/now",
            "schedule/now",
        ):
            meta, body = await fetch(session, path)
            name = path.replace("/", "_") + ".json"
            (out / name).write_bytes(body)
            say("INFO", f"saved {name} {meta}")

        detector = EventDetector(args.team)
        last_hash = None
        seen: dict[int, dict[str, Any]] = {}
        last_state: tuple | None = None
        last_period = None
        seq = 0
        final_at: float | None = None
        etag = last_modified = None
        tested_conditional = False

        while True:
            try:
                meta, body = await fetch(session, f"gamecenter/{game_id}/play-by-play")
            except Exception as err:
                say("ERROR", f"fetch failed: {err!r}")
                await asyncio.sleep(args.interval)
                continue
            digest = hashlib.sha1(body).hexdigest()
            changed = digest != last_hash
            meta.update(t=datetime.now(UTC).isoformat(), changed=changed)
            polls.write(json.dumps(meta) + "\n")
            polls.flush()

            if not tested_conditional and (meta.get("etag") or meta.get("last-modified")):
                etag, last_modified = meta.get("etag"), meta.get("last-modified")
                cond = {}
                if etag:
                    cond["If-None-Match"] = etag
                if last_modified:
                    cond["If-Modified-Since"] = last_modified
                cmeta, _ = await fetch(session, f"gamecenter/{game_id}/play-by-play", cond)
                say("INFO", f"conditional request {cond} -> status {cmeta['status']} bytes {cmeta['bytes']}")
                tested_conditional = True

            if changed:
                last_hash = digest
                seq += 1
                (out / "snapshots" / f"{seq:04d}.json").write_bytes(body)
                raw = json.loads(body)
                plays = {p["eventId"]: p for p in raw.get("plays", []) if "eventId" in p}

                for eid, play in plays.items():
                    old = seen.get(eid)
                    if old is None:
                        if play.get("typeDescKey") in TRACKED_TYPES:
                            say("PLAY", describe(play))
                    elif old != play:
                        changes = []
                        for key in sorted(set(old) | set(play)):
                            if key == "details":
                                od, nd = old.get("details") or {}, play.get("details") or {}
                                for dk in sorted(set(od) | set(nd)):
                                    if od.get(dk) != nd.get(dk):
                                        changes.append(f"details.{dk}: {od.get(dk)!r} -> {nd.get(dk)!r}")
                            elif old.get(key) != play.get(key):
                                changes.append(f"{key}: {old.get(key)!r} -> {play.get(key)!r}")
                        if (
                            play.get("typeDescKey") in TRACKED_TYPES
                            or old.get("typeDescKey") in TRACKED_TYPES
                        ):
                            say("AMEND", f"{eid} {play.get('typeDescKey')} " + "; ".join(changes))
                for eid in set(seen) - set(plays):
                    say("REMOVED", f"{eid} {describe(seen[eid])}")
                seen = plays

                clock = raw.get("clock") or {}
                state = (
                    raw.get("gameState"),
                    raw.get("periodDescriptor", {}).get("number"),
                    clock.get("inIntermission"),
                )
                if state != last_state:
                    say(
                        "STATE",
                        f"gameState={state[0]} period={state[1]} inIntermission={state[2]} clock={clock.get('timeRemaining')} running={clock.get('running')} score={raw.get('awayTeam', {}).get('score')}-{raw.get('homeTeam', {}).get('score')}",
                    )
                    last_state = state
                if state[1] != last_period:
                    _meta_l, body_l = await fetch(session, f"gamecenter/{game_id}/landing")
                    (out / f"landing_p{state[1]}.json").write_bytes(body_l)
                    last_period = state[1]

                snap = parse_play_by_play(raw)
                for event in detector.process(snap):
                    d = event.data
                    extra = ""
                    if d.get("scorer"):
                        a1 = (d.get("primary_assist") or {}).get("name")
                        a2 = (d.get("secondary_assist") or {}).get("name")
                        extra = f" scorer={d['scorer'].get('name')} assists={a1},{a2} strength={d.get('strength')}"
                    if d.get("infraction"):
                        extra = f" {(d.get('committed_by') or {}).get('name')} {d.get('infraction')} {d.get('duration_min')}min"
                    say(
                        "EVENT",
                        f"{event.type} {d.get('period_label')} {d.get('time_in_period') or ''} score={d.get('score')}{extra}",
                    )
                    events_log.write(
                        json.dumps({"t": datetime.now(UTC).isoformat(), **d}, default=str) + "\n"
                    )
                    events_log.flush()

                if raw.get("gameState") in ("OVER", "FINAL", "OFF") and final_at is None:
                    final_at = time.monotonic()
                    say("INFO", f"game final, polling {args.after_final}s more for late edits")
            if final_at and time.monotonic() - final_at > args.after_final:
                say("DONE", f"{seq} snapshots recorded in {out}")
                return
            await asyncio.sleep(args.interval)


if __name__ == "__main__":
    asyncio.run(main())
