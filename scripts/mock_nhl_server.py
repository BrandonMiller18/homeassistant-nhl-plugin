"""Mock NHL API that plays a scripted game, for testing without a real game.

Usage:
    python scripts/mock_nhl_server.py --team BOS --opponent TOR --step 20

Then in Home Assistant: NHL Companion > Configure > "Advanced: NHL API base URL"
set to http://<this-machine>:8765/v1. Each step advances the game: pre-game,
puck drop, goals, a delayed penalty and power play, a goal whose assist is posted
a step later, intermission, an overturned goal, and a final.
Use --manual and POST /mock/next to advance by hand.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import logging
from pathlib import Path
import sys

from aiohttp import web

sys.path.insert(0, str(Path(__file__).parent))
from fake_nhl import FakeGame, _roster, club_schedule, league_schedule, standings

_LOGGER = logging.getLogger("mock_nhl")


def build_script(game: FakeGame, team: str, opp: str) -> list[tuple[str, Callable[[], None]]]:
    t = _roster(team)
    o = _roster(opp)
    state: dict[str, int] = {}

    def disallowed_goal() -> None:
        state["goal"] = game.goal(team, t[2][0], t[0][0], time_in_period="06:30")

    def opponent_penalty() -> None:
        # Posted with the pre-penalty situationCode; the situation block flips to PP at once
        game.penalty(opp, o[1][0], t[0][0], "tripping", time_in_period="09:30")
        game.power_play(team, "02:00")

    def power_play_goal() -> None:
        # Live feeds often post a goal without assists and add them a poll or two later
        state["pp_goal"] = game.goal(team, t[1][0], situation="1451", time_in_period="10:45")
        game.power_play(None)

    return [
        ("pre-game", game.pregame),
        ("puck drop: 1st period", lambda: game.start_period(1)),
        ("team goal", lambda: game.goal(team, t[0][0], t[1][0], t[2][0], time_in_period="04:12")),
        ("delayed penalty on opponent (extra attacker, not a power play)", lambda: game.delayed_penalty(opp)),
        ("opponent penalty, team power play", opponent_penalty),
        ("team power-play goal, assists not posted yet", power_play_goal),
        (
            "assist added to the power-play goal",
            lambda: game.amend(state["pp_goal"], assist1PlayerId=t[0][0]),
        ),
        ("opponent goal", lambda: game.goal(opp, o[0][0], o[1][0], time_in_period="15:02")),
        ("end of 1st, intermission", game.end_period),
        ("intermission clock ends (puck drop about 2 minutes later)", game.end_intermission),
        ("2nd period starts", lambda: game.start_period(2)),
        ("team goal (will be overturned)", disallowed_goal),
        ("goal overturned on review", lambda: game.remove_play(state["goal"], team)),
        ("team penalty", lambda: game.penalty(team, t[1][0], o[0][0], "hooking", time_in_period="12:00")),
        ("end of 2nd", game.end_period),
        ("3rd period starts", lambda: game.start_period(3)),
        ("final: team wins", game.final),
    ]


def make_app(team: str, opp: str, start_in: int, step: int, manual: bool) -> web.Application:
    start = datetime.now(UTC) + timedelta(minutes=start_in)
    # Unique ids per run: real NHL ids are never reused, and HA persists seen plays per game
    base_id = 2025090000 + int(start.timestamp()) % 9000 * 10
    game = FakeGame(home=team, away=opp, start=start, game_id=base_id)
    later = FakeGame(home=opp, away=team, start=start + timedelta(days=2), game_id=base_id + 1)
    script = build_script(game, team, opp)
    position = {"i": 0}

    def advance() -> str:
        if position["i"] >= len(script):
            return "game over"
        label, action = script[position["i"]]
        action()
        position["i"] += 1
        _LOGGER.info("Step %s/%s: %s (score %s)", position["i"], len(script), label, game.score)
        return label

    async def auto(app: web.Application) -> None:
        async def loop() -> None:
            while position["i"] < len(script):
                await asyncio.sleep(step)
                advance()

        task = asyncio.create_task(loop())
        yield
        task.cancel()

    routes = web.RouteTableDef()

    @routes.get("/v1/schedule/{date}")
    async def schedule(_: web.Request) -> web.Response:
        return web.json_response(league_schedule([game, later], start=start - timedelta(hours=6)))

    @routes.get("/v1/standings/now")
    async def stand(_: web.Request) -> web.Response:
        return web.json_response(standings())

    @routes.get("/v1/club-schedule-season/{abbrev}/now")
    async def club(request: web.Request) -> web.Response:
        return web.json_response(club_schedule(request.match_info["abbrev"].upper(), [game, later]))

    @routes.get("/v1/gamecenter/{game_id}/play-by-play")
    async def pbp(request: web.Request) -> web.Response:
        gid = int(request.match_info["game_id"])
        target = game if gid == game.id else later if gid == later.id else None
        if target is None:
            raise web.HTTPNotFound
        return web.json_response(target.play_by_play())

    @routes.post("/mock/next")
    async def next_step(_: web.Request) -> web.Response:
        return web.json_response({"step": advance(), "position": position["i"], "score": game.score})

    @routes.get("/mock/state")
    async def mock_state(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "position": position["i"],
                "steps": [s[0] for s in script],
                "state": game.state,
                "score": game.score,
            }
        )

    app = web.Application()
    app.add_routes(routes)
    if not manual:
        app.cleanup_ctx.append(auto)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--team", default="BOS", help="Followed team abbreviation (home team)")
    parser.add_argument("--opponent", default="TOR")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--step", type=int, default=20, help="Seconds between game steps")
    parser.add_argument("--start-in", type=int, default=10, help="Minutes until scheduled puck drop")
    parser.add_argument("--manual", action="store_true", help="Only advance on POST /mock/next")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    app = make_app(args.team.upper(), args.opponent.upper(), args.start_in, args.step, args.manual)
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
