"""Team game stats and scoring summary computed from a play-by-play snapshot.

Pure logic with no Home Assistant imports. Ownership rules were checked against
live data (STL@OTT, 2026-10-13): eventOwnerTeamId is the acting team for hits,
faceoffs (winner), giveaways, takeaways, shots and penalties (penalized team),
but the shooting team for blocked shots, so blocks are credited via the blocker.
"""

from __future__ import annotations

from typing import Any

from .event_detector import period_label, strength_for
from .models import GameSnapshot, TeamSide

COUNTED = {"hit": "hits", "giveaway": "giveaways", "takeaway": "takeaways"}


def _empty() -> dict[str, Any]:
    return {
        "shots_on_goal": None,
        "hits": 0,
        "blocked_shots": 0,
        "faceoff_wins": 0,
        "faceoff_pct": None,
        "giveaways": 0,
        "takeaways": 0,
        "penalty_minutes": 0,
        "power_play_goals": 0,
    }


def game_stats(snap: GameSnapshot, team: TeamSide, opponent: TeamSide) -> dict[str, Any]:
    """Return {"team": {...}, "opponent": {...}, "goals": [...]} for the followed team."""
    sides = {team.id: _empty(), opponent.id: _empty()}
    other = {team.id: opponent.id, opponent.id: team.id}
    home_id = snap.game.home.id
    goals: list[dict[str, Any]] = []

    for play in snap.plays:
        owner = play.owner_team_id
        if owner not in sides:
            continue
        d = play.details
        key = play.type_key
        if key in COUNTED:
            sides[owner][COUNTED[key]] += 1
        elif key == "faceoff":
            sides[owner]["faceoff_wins"] += 1
        elif key == "blocked-shot":
            # Owner is the shooting team; a shot blocked by a teammate is not a block
            blocker = snap.player(int(d["blockingPlayerId"])) if d.get("blockingPlayerId") else None
            if blocker is None or blocker.team_id != owner:
                sides[other[owner]]["blocked_shots"] += 1
        elif key == "penalty":
            sides[owner]["penalty_minutes"] += int(d.get("duration") or 0)
        elif key == "goal":
            strength = strength_for(play.situation_code, owner == home_id)
            if strength == "pp":
                sides[owner]["power_play_goals"] += 1
            goals.append(_goal_line(snap, play, owner == team.id, team.id == home_id, strength))

    total_faceoffs = sides[team.id]["faceoff_wins"] + sides[opponent.id]["faceoff_wins"]
    for side_id, side in ((team.id, team), (opponent.id, opponent)):
        stats = sides[side_id]
        stats["shots_on_goal"] = side.sog
        if total_faceoffs:
            stats["faceoff_pct"] = round(100 * stats["faceoff_wins"] / total_faceoffs, 1)
    return {"team": sides[team.id], "opponent": sides[opponent.id], "goals": goals}


def _name(snap: GameSnapshot, player_id: Any) -> str | None:
    if player_id is None:
        return None
    player = snap.player(int(player_id))
    return player.name if player else None


def _goal_line(
    snap: GameSnapshot, play: Any, is_team: bool, team_is_home: bool, strength: str | None
) -> dict[str, Any]:
    d = play.details
    own, opp = ("homeScore", "awayScore") if team_is_home else ("awayScore", "homeScore")
    assists = [n for n in (_name(snap, d.get("assist1PlayerId")), _name(snap, d.get("assist2PlayerId"))) if n]
    return {
        "side": "team" if is_team else "opponent",
        "period_label": period_label(play.period, play.period_type),
        "time_in_period": play.time_in_period,
        "scorer": _name(snap, d.get("scoringPlayerId")),
        "assists": assists,
        "strength": strength,
        "score": {"team": d.get(own), "opponent": d.get(opp)},
    }
