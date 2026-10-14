"""Data models for NHL Companion. No Home Assistant imports."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class TeamSide:
    """One team in a game."""

    id: int | None
    abbrev: str
    name: str
    logo: str | None = None
    score: int | None = None
    sog: int | None = None


@dataclass(slots=True)
class Game:
    """A scheduled, live or finished game."""

    id: int
    season: int | None
    game_type: int | None
    start_utc: datetime | None
    state: str
    schedule_state: str
    venue: str | None
    home: TeamSide
    away: TeamSide
    period: int | None = None
    period_type: str | None = None
    clock: str | None = None
    in_intermission: bool = False
    last_period_type: str | None = None
    # From the play-by-play "situation" block, which is only present when the teams
    # are not at even strength (and occasionally drops out for one update)
    has_situation: bool = False
    power_play_abbrev: str | None = None
    power_play_remaining: str | None = None

    def side_for(self, abbrev: str) -> tuple[TeamSide, TeamSide, bool] | None:
        """Return (team, opponent, is_home) for a team abbreviation."""
        if self.home.abbrev == abbrev:
            return self.home, self.away, True
        if self.away.abbrev == abbrev:
            return self.away, self.home, False
        return None

    def as_dict(self) -> dict[str, Any]:
        """Serialize for websocket/diagnostics."""
        data = asdict(self)
        data["start_utc"] = self.start_utc.isoformat() if self.start_utc else None
        return data


@dataclass(slots=True)
class Player:
    """A rostered player in a game."""

    id: int
    name: str
    first_name: str
    last_name: str
    number: int | None
    position: str | None
    team_id: int | None
    headshot: str | None

    def as_payload(self, season_total: int | None = None) -> dict[str, Any]:
        """Serialize for event payloads."""
        return {
            "id": self.id,
            "name": self.name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "number": self.number,
            "position": self.position,
            "headshot": self.headshot,
            "season_total": season_total,
        }


@dataclass(slots=True)
class Play:
    """A single play-by-play entry."""

    event_id: int
    sort_order: int
    type_key: str
    period: int | None
    period_type: str | None
    time_in_period: str | None
    time_remaining: str | None
    situation_code: str | None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def owner_team_id(self) -> int | None:
        """Team the play belongs to (scorer's team, penalized team...)."""
        return self.details.get("eventOwnerTeamId")


@dataclass(slots=True)
class GameSnapshot:
    """Full live state of a game from the play-by-play endpoint."""

    game: Game
    plays: list[Play]
    roster: dict[int, Player]

    def player(self, player_id: int | None) -> Player | None:
        """Look up a player by id."""
        if player_id is None:
            return None
        return self.roster.get(player_id)


@dataclass(slots=True)
class Standing:
    """One team's row in the standings."""

    abbrev: str
    name: str
    logo: str | None
    conference: str | None
    division: str | None
    games_played: int
    wins: int
    losses: int
    ot_losses: int
    points: int
    point_pct: float | None
    goal_differential: int | None
    league_rank: int | None
    conference_rank: int | None
    division_rank: int | None
    wildcard_rank: int | None
    streak: str | None
    last_10: str | None

    def as_dict(self) -> dict[str, Any]:
        """Serialize for websocket/attributes."""
        return asdict(self)


@dataclass(slots=True)
class ScheduleDay:
    """All league games on one date."""

    date: str
    games: list[Game]

    def as_dict(self) -> dict[str, Any]:
        """Serialize for websocket."""
        return {"date": self.date, "games": [g.as_dict() for g in self.games]}


@dataclass(slots=True)
class NhlEvent:
    """An event detected for a followed team."""

    type: str
    data: dict[str, Any]
    # Stable key used to avoid firing the same event twice
    key: str
