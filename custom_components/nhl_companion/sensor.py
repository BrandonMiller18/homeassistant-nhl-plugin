"""Sensors for NHL Companion."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NhlConfigEntry
from .const import FINISHED_STATES, LIVE_STATES, LOGO_URL_TEMPLATE, STATE_FUTURE, STATE_PRE
from .coordinator import LeagueCoordinator, TeamCoordinator
from .entity import NhlTeamEntity, team_device_info
from .event_detector import period_label
from .models import Game

STATUS_OPTIONS = [
    "no_game",
    "scheduled",
    "pre_game",
    "live",
    "intermission",
    "final",
    "postponed",
]


def game_status(game: Game | None) -> str:
    """Map an NHL game to a simple status."""
    if game is None:
        return "no_game"
    if game.schedule_state != "OK":
        return "postponed"
    if game.state in LIVE_STATES:
        return "intermission" if game.in_intermission else "live"
    if game.state in FINISHED_STATES:
        return "final"
    if game.state == STATE_PRE:
        return "pre_game"
    if game.state == STATE_FUTURE:
        return "scheduled"
    return "scheduled"


def _latest(
    events: dict[str, dict[str, Any]], types: tuple[str, ...], game_id: int | None = None
) -> dict[str, Any] | None:
    """Most recently fired event payload of the given types (optionally for one game)."""
    found = [e for t in types if (e := events.get(t)) and (game_id is None or e.get("game_id") == game_id)]
    return max(found, key=lambda e: e.get("fired_at") or "", default=None)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NhlConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    team = entry.runtime_data.team
    league = entry.runtime_data.league
    async_add_entities(
        [
            GameStatusSensor(team),
            ScoreSensor(team, "team_score", own=True),
            ScoreSensor(team, "opponent_score", own=False),
            ShotsSensor(team, "team_shots", own=True),
            ShotsSensor(team, "opponent_shots", own=False),
            NextGameSensor(team),
            LastGameSensor(team),
            StandingSensor(league, team),
        ]
    )


class GameStatusSensor(NhlTeamEntity, SensorEntity):
    """Current/next game status with full game details as attributes."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUS_OPTIONS

    def __init__(self, coordinator: TeamCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "game_status")
        self._attr_entity_picture = LOGO_URL_TEMPLATE.format(abbrev=self.team_abbrev)

    @property
    def native_value(self) -> str:
        """Return the status."""
        return game_status(self.coordinator.data.current_game)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Game details for dashboards and templates."""
        data = self.coordinator.data
        game = data.current_game
        if game is None or (sides := game.side_for(self.team_abbrev)) is None:
            return {}
        team, opp, is_home = sides
        return {
            "game_id": game.id,
            "team_abbrev": team.abbrev,
            "team_name": team.name,
            "team_logo": team.logo,
            "opponent_abbrev": opp.abbrev,
            "opponent_name": opp.name,
            "opponent_logo": opp.logo,
            "is_home": is_home,
            "start_time": game.start_utc.isoformat() if game.start_utc else None,
            "venue": game.venue,
            "nhl_state": game.state,
            "period": game.period,
            "period_label": period_label(game.period, game.period_type),
            "clock": game.clock,
            "in_intermission": game.in_intermission,
            "team_score": team.score,
            "opponent_score": opp.score,
            "team_sog": team.sog,
            "opponent_sog": opp.sog,
            "strength": data.strength,
            "power_play_time_remaining": data.power_play_remaining,
            "team_stats": data.stats["team"] if data.stats else None,
            "opponent_stats": data.stats["opponent"] if data.stats else None,
            "goals": data.stats["goals"] if data.stats else [],
            "three_stars": data.three_stars,
            "last_goal": _latest(data.last_events, ("team_goal", "opponent_goal", "goal_updated")),
            "last_goal_video": _latest(data.last_events, ("goal_highlight",), game.id),
        }


class ScoreSensor(NhlTeamEntity, SensorEntity):
    """Team or opponent score in the current game."""

    def __init__(self, coordinator: TeamCoordinator, key: str, own: bool) -> None:
        """Initialize."""
        super().__init__(coordinator, key)
        self._own = own

    @property
    def native_value(self) -> int | None:
        """Return the score, or None when no game has started."""
        game = self.coordinator.data.current_game
        if game is None or game.state not in LIVE_STATES | FINISHED_STATES:
            return None
        sides = game.side_for(self.team_abbrev)
        if sides is None:
            return None
        side = sides[0] if self._own else sides[1]
        return side.score or 0


class ShotsSensor(NhlTeamEntity, SensorEntity):
    """Team or opponent shots on goal in the current game, for small displays."""

    def __init__(self, coordinator: TeamCoordinator, key: str, own: bool) -> None:
        """Initialize."""
        super().__init__(coordinator, key)
        self._own = own

    @property
    def native_value(self) -> int | None:
        """Return shots on goal, or None when no game has started."""
        game = self.coordinator.data.current_game
        if game is None or game.state not in LIVE_STATES | FINISHED_STATES:
            return None
        sides = game.side_for(self.team_abbrev)
        if sides is None:
            return None
        side = sides[0] if self._own else sides[1]
        return side.sog or 0


class NextGameSensor(NhlTeamEntity, SensorEntity):
    """Start time of the next (or current) game."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: TeamCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "next_game")

    @property
    def native_value(self) -> datetime | None:
        """Return puck drop time."""
        game = self.coordinator.data.next_game
        return game.start_utc if game else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Opponent and venue."""
        game = self.coordinator.data.next_game
        if game is None or (sides := game.side_for(self.team_abbrev)) is None:
            return {}
        _, opp, is_home = sides
        return {
            "game_id": game.id,
            "opponent_abbrev": opp.abbrev,
            "opponent_name": opp.name,
            "opponent_logo": opp.logo,
            "is_home": is_home,
            "venue": game.venue,
            "matchup": f"{'vs' if is_home else '@'} {opp.abbrev}",
        }


class LastGameSensor(NhlTeamEntity, SensorEntity):
    """Result of the most recent finished game, e.g. W 4-2."""

    def __init__(self, coordinator: TeamCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "last_game")

    def _sides(self):
        game = self.coordinator.data.last_game
        if game is None:
            return None, None
        return game, game.side_for(self.team_abbrev)

    @property
    def native_value(self) -> str | None:
        """Return W/L/OTL with score."""
        game, sides = self._sides()
        if game is None or sides is None:
            return None
        team, opp, _ = sides
        ts, os_ = team.score or 0, opp.score or 0
        if ts > os_:
            result = "W"
        elif game.last_period_type in ("OT", "SO"):
            result = "OTL"
        else:
            result = "L"
        suffix = f" ({game.last_period_type})" if game.last_period_type in ("OT", "SO") else ""
        return f"{result} {ts}-{os_}{suffix}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Opponent and date."""
        game, sides = self._sides()
        if game is None or sides is None:
            return {}
        _, opp, is_home = sides
        return {
            "game_id": game.id,
            "opponent_abbrev": opp.abbrev,
            "opponent_name": opp.name,
            "is_home": is_home,
            "start_time": game.start_utc.isoformat() if game.start_utc else None,
        }


class StandingSensor(CoordinatorEntity[LeagueCoordinator], SensorEntity):
    """League points with the full standings row as attributes."""

    _attr_has_entity_name = True
    _attr_translation_key = "standing"
    _attr_native_unit_of_measurement = "pts"

    def __init__(self, league: LeagueCoordinator, team: TeamCoordinator) -> None:
        """Initialize."""
        super().__init__(league)
        entry = team.config_entry
        self.team_abbrev = team.team_abbrev
        self._attr_unique_id = f"{entry.entry_id}_standing"
        self._attr_device_info = team_device_info(entry.entry_id, team.team_abbrev, entry.title)

    @property
    def native_value(self) -> int | None:
        """Return points."""
        row = self.coordinator.data.standing_for(self.team_abbrev) if self.coordinator.data else None
        return row.points if row else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Record and ranks."""
        row = self.coordinator.data.standing_for(self.team_abbrev) if self.coordinator.data else None
        if row is None:
            return {}
        attrs = row.as_dict()
        attrs["record"] = f"{row.wins}-{row.losses}-{row.ot_losses}"
        return attrs
