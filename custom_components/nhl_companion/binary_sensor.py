"""Binary sensors for NHL Companion."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import NhlConfigEntry
from .const import LIVE_STATES
from .coordinator import TeamCoordinator
from .entity import NhlTeamEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NhlConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    team = entry.runtime_data.team
    async_add_entities([GameTodaySensor(team), GameLiveSensor(team), PowerPlaySensor(team)])


class GameTodaySensor(NhlTeamEntity, BinarySensorEntity):
    """On when the team plays today (local time)."""

    def __init__(self, coordinator: TeamCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "game_today")

    @property
    def is_on(self) -> bool:
        """Return true on game day."""
        today = dt_util.now().date()
        return any(
            g.start_utc is not None
            and g.schedule_state == "OK"
            and dt_util.as_local(g.start_utc).date() == today
            for g in self.coordinator.data.games
        )


class GameLiveSensor(NhlTeamEntity, BinarySensorEntity):
    """On while the team's game is in progress (including intermissions)."""

    def __init__(self, coordinator: TeamCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "game_live")

    @property
    def is_on(self) -> bool:
        """Return true during a live game."""
        game = self.coordinator.data.current_game
        return game is not None and game.state in LIVE_STATES


class PowerPlaySensor(NhlTeamEntity, BinarySensorEntity):
    """On while the team has a man advantage."""

    def __init__(self, coordinator: TeamCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "power_play")

    @property
    def is_on(self) -> bool:
        """Return true on the power play."""
        return self.coordinator.data.strength == "pp"

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Raw strength (ev, pp or sh) and power play time left."""
        data = self.coordinator.data
        return {"strength": data.strength, "time_remaining": data.power_play_remaining}
