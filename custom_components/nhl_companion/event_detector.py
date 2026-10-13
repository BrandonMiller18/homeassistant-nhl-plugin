"""Turn successive play-by-play snapshots into team events.

Pure logic with no Home Assistant imports, so it can be tested by replaying
snapshot sequences.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .const import (
    EVT_GAME_END_LOSS,
    EVT_GAME_END_OTL,
    EVT_GAME_END_WIN,
    EVT_GAME_START,
    EVT_GOAL_REVERSED,
    EVT_INTERMISSION_END,
    EVT_INTERMISSION_START,
    EVT_OPPONENT_GOAL,
    EVT_OPPONENT_PENALTY,
    EVT_PERIOD_END,
    EVT_PERIOD_START,
    EVT_TEAM_GOAL,
    EVT_TEAM_PENALTY,
    FINISHED_STATES,
    LIVE_STATES,
)
from .models import Game, GameSnapshot, NhlEvent, Play, TeamSide

ORDINALS = {1: "1st", 2: "2nd", 3: "3rd"}


def period_label(period: int | None, period_type: str | None) -> str | None:
    """Human label for a period: 1st, 2nd, 3rd, OT, 2OT, SO."""
    if period is None:
        return None
    if period_type == "SO":
        return "SO"
    if period_type == "OT" or period > 3:
        extra = period - 3
        return "OT" if extra <= 1 else f"{extra}OT"
    return ORDINALS.get(period, f"{period}th")


def strength_for(situation_code: str | None, scorer_is_home: bool) -> str | None:
    """Classify strength from the 4-digit situationCode.

    Digits are: away goalie in net, away skaters, home skaters, home goalie in net.
    Returns ev, pp, sh or en (empty net against).
    """
    if not situation_code or len(situation_code) != 4 or not situation_code.isdigit():
        return None
    away_goalie, away_skaters, home_skaters, home_goalie = (int(c) for c in situation_code)
    if scorer_is_home:
        own, opp, own_goalie, opp_goalie = home_skaters, away_skaters, home_goalie, away_goalie
    else:
        own, opp, own_goalie, opp_goalie = away_skaters, home_skaters, away_goalie, home_goalie
    if opp_goalie == 0:
        return "en"
    # An extra attacker for a pulled goalie is not a power play
    if own_goalie == 0:
        own -= 1
    if own > opp:
        return "pp"
    if own < opp:
        return "sh"
    return "ev"


def humanize(key: str | None) -> str | None:
    """hooking -> Hooking, delaying-game-puck-over-glass -> Delaying game puck over glass."""
    if not key:
        return None
    words = key.replace("-", " ").strip()
    return words[:1].upper() + words[1:]


@dataclass
class DetectorState:
    """Serializable detector memory for one game."""

    game_id: int
    seen_ids: set[int] = field(default_factory=set)
    # goal event_id -> {side, scorer, period_label, time_in_period}
    goals: dict[int, dict[str, Any]] = field(default_factory=dict)
    team_score: int = 0
    opponent_score: int = 0
    game_state: str | None = None
    in_intermission: bool = False
    emitted: set[str] = field(default_factory=set)

    def as_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict."""
        return {
            "game_id": self.game_id,
            "seen_ids": sorted(self.seen_ids),
            "goals": {str(k): v for k, v in self.goals.items()},
            "team_score": self.team_score,
            "opponent_score": self.opponent_score,
            "game_state": self.game_state,
            "in_intermission": self.in_intermission,
            "emitted": sorted(self.emitted),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DetectorState:
        """Restore from as_dict output."""
        return cls(
            game_id=int(data["game_id"]),
            seen_ids={int(i) for i in data.get("seen_ids", [])},
            goals={
                int(k): v if isinstance(v, dict) else {"side": v}
                for k, v in (data.get("goals") or {}).items()
            },
            team_score=int(data.get("team_score", 0)),
            opponent_score=int(data.get("opponent_score", 0)),
            game_state=data.get("game_state"),
            in_intermission=bool(data.get("in_intermission", False)),
            emitted=set(data.get("emitted", [])),
        )


class EventDetector:
    """Diff play-by-play snapshots for one followed team."""

    def __init__(self, team_abbrev: str, state: DetectorState | None = None) -> None:
        """Initialize with optional restored state."""
        self.team_abbrev = team_abbrev
        self.state = state

    def process(self, snap: GameSnapshot) -> list[NhlEvent]:
        """Return new events since the previous snapshot.

        The first snapshot of a game is a baseline and returns nothing, so a
        restart or a mid-game setup never replays old goals.
        """
        game = snap.game
        sides = game.side_for(self.team_abbrev)
        if sides is None:
            return []
        team, opponent, is_home = sides

        if self.state is None or self.state.game_id != game.id:
            self.state = self._baseline(snap, team, opponent)
            return []

        state = self.state
        events: list[NhlEvent] = []
        base = self._base_payload(game, team, opponent, is_home)

        # Game start
        if (
            game.state in LIVE_STATES
            and "game_start" not in state.emitted
            and state.game_state not in LIVE_STATES | FINISHED_STATES
        ):
            state.emitted.add("game_start")
            events.append(self._event(EVT_GAME_START, base, f"{game.id}:game_start"))

        # New plays
        current_ids = {p.event_id for p in snap.plays}
        for play in snap.plays:
            if play.event_id in state.seen_ids:
                continue
            state.seen_ids.add(play.event_id)
            event = self._play_event(snap, play, base, team, is_home)
            if event is not None:
                events.append(event)

        # Goals that vanished from the feed were overturned
        reversed_ids = [gid for gid in state.goals if gid not in current_ids]
        for gid in reversed_ids:
            goal = state.goals.pop(gid)
            events.append(
                self._event(
                    EVT_GOAL_REVERSED,
                    {
                        **base,
                        "side": goal.get("side"),
                        "event_id": gid,
                        "scorer": goal.get("scorer"),
                        "original_period_label": goal.get("period_label"),
                        "original_time_in_period": goal.get("time_in_period"),
                    },
                    f"{game.id}:{gid}:reversed",
                )
            )

        # Fallback: score dropped without a vanished goal id
        team_score = team.score or 0
        opp_score = opponent.score or 0
        if not reversed_ids:
            for side, old, new in (
                ("team", state.team_score, team_score),
                ("opponent", state.opponent_score, opp_score),
            ):
                if new < old:
                    events.append(
                        self._event(
                            EVT_GOAL_REVERSED,
                            {**base, "side": side, "event_id": None},
                            f"{game.id}:{side}:{new}:reversed",
                        )
                    )
        state.team_score = team_score
        state.opponent_score = opp_score

        # Intermission transitions
        if game.in_intermission != state.in_intermission and game.state in LIVE_STATES:
            evt = EVT_INTERMISSION_START if game.in_intermission else EVT_INTERMISSION_END
            events.append(self._event(evt, base, f"{game.id}:{evt}:{game.period}"))
        state.in_intermission = game.in_intermission

        # Game end
        if game.state in FINISHED_STATES and "game_end" not in state.emitted:
            state.emitted.add("game_end")
            events.append(self._game_end(snap, base, team_score, opp_score))

        state.game_state = game.state
        return events

    def _baseline(self, snap: GameSnapshot, team: TeamSide, opponent: TeamSide) -> DetectorState:
        game = snap.game
        state = DetectorState(
            game_id=game.id,
            seen_ids={p.event_id for p in snap.plays},
            team_score=team.score or 0,
            opponent_score=opponent.score or 0,
            game_state=game.state,
            in_intermission=game.in_intermission,
        )
        for play in snap.plays:
            if play.type_key == "goal":
                state.goals[play.event_id] = {
                    "side": "team" if play.owner_team_id == team.id else "opponent",
                    "scorer": self._player(snap, play.details.get("scoringPlayerId")),
                    "period_label": period_label(play.period, play.period_type),
                    "time_in_period": play.time_in_period,
                }
        if game.state in LIVE_STATES | FINISHED_STATES:
            state.emitted.add("game_start")
        if game.state in FINISHED_STATES:
            state.emitted.add("game_end")
        return state

    @staticmethod
    def _event(evt_type: str, payload: dict[str, Any], key: str) -> NhlEvent:
        return NhlEvent(type=evt_type, data={"type": evt_type, **payload}, key=key)

    @staticmethod
    def _base_payload(game: Game, team: TeamSide, opponent: TeamSide, is_home: bool) -> dict[str, Any]:
        return {
            "game_id": game.id,
            "team_abbrev": team.abbrev,
            "team_name": team.name,
            "opponent_abbrev": opponent.abbrev,
            "opponent_name": opponent.name,
            "is_home": is_home,
            "period": game.period,
            "period_type": game.period_type,
            "period_label": period_label(game.period, game.period_type),
            "score": {"team": team.score or 0, "opponent": opponent.score or 0},
        }

    def _play_event(
        self,
        snap: GameSnapshot,
        play: Play,
        base: dict[str, Any],
        team: TeamSide,
        is_home: bool,
    ) -> NhlEvent | None:
        game = snap.game
        d = play.details
        play_base = {
            **base,
            "event_id": play.event_id,
            "period": play.period,
            "period_type": play.period_type,
            "period_label": period_label(play.period, play.period_type),
            "time_in_period": play.time_in_period,
            "time_remaining": play.time_remaining,
        }
        is_team = play.owner_team_id is not None and play.owner_team_id == team.id
        key = f"{game.id}:{play.event_id}"

        if play.type_key == "goal":
            scorer_is_home = is_home if is_team else not is_home
            payload = {
                **play_base,
                "scorer": self._player(snap, d.get("scoringPlayerId"), d.get("scoringPlayerTotal")),
                "primary_assist": self._player(snap, d.get("assist1PlayerId"), d.get("assist1PlayerTotal")),
                "secondary_assist": self._player(snap, d.get("assist2PlayerId"), d.get("assist2PlayerTotal")),
                "strength": strength_for(play.situation_code, scorer_is_home),
                "shot_type": d.get("shotType"),
                "highlight_url": d.get("highlightClipSharingUrl"),
            }
            if "homeScore" in d and "awayScore" in d:
                home_score, away_score = d["homeScore"], d["awayScore"]
                payload["score"] = (
                    {"team": home_score, "opponent": away_score}
                    if is_home
                    else {"team": away_score, "opponent": home_score}
                )
            payload["empty_net"] = payload["strength"] == "en"
            self.state.goals[play.event_id] = {  # type: ignore[union-attr]
                "side": "team" if is_team else "opponent",
                "scorer": payload["scorer"],
                "period_label": play_base["period_label"],
                "time_in_period": play.time_in_period,
            }
            return self._event(EVT_TEAM_GOAL if is_team else EVT_OPPONENT_GOAL, payload, key)

        if play.type_key == "penalty":
            payload = {
                **play_base,
                "committed_by": self._player(snap, d.get("committedByPlayerId")),
                "drawn_by": self._player(snap, d.get("drawnByPlayerId")),
                "served_by": self._player(snap, d.get("servedByPlayerId")),
                "infraction": humanize(d.get("descKey")),
                "penalty_type": d.get("typeCode"),
                "duration_min": d.get("duration"),
            }
            return self._event(EVT_TEAM_PENALTY if is_team else EVT_OPPONENT_PENALTY, payload, key)

        if play.type_key == "period-start":
            return self._event(EVT_PERIOD_START, play_base, key)
        if play.type_key == "period-end":
            return self._event(EVT_PERIOD_END, play_base, key)
        return None

    @staticmethod
    def _player(snap: GameSnapshot, player_id: Any, season_total: Any = None) -> dict[str, Any] | None:
        if player_id is None:
            return None
        player = snap.player(int(player_id))
        if player is None:
            return {"id": int(player_id), "name": None, "season_total": season_total}
        return player.as_payload(season_total)

    @staticmethod
    def _game_end(snap: GameSnapshot, base: dict[str, Any], team_score: int, opp_score: int) -> NhlEvent:
        game = snap.game
        last_type = game.last_period_type or game.period_type
        if team_score > opp_score:
            evt = EVT_GAME_END_WIN
        elif last_type in ("OT", "SO"):
            evt = EVT_GAME_END_OTL
        else:
            evt = EVT_GAME_END_LOSS
        payload = {**base, "last_period_type": last_type}
        return NhlEvent(type=evt, data={"type": evt, **payload}, key=f"{game.id}:game_end")
