"""Master on/off switch for game alerts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import NhlConfigEntry
from .coordinator import TeamCoordinator
from .entity import NhlTeamEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NhlConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the alerts switch."""
    async_add_entities([GameAlertsSwitch(entry.runtime_data.team)])


class GameAlertsSwitch(NhlTeamEntity, SwitchEntity, RestoreEntity):
    """When off, no events fire. Sensors keep updating."""

    def __init__(self, coordinator: TeamCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "game_alerts")

    async def async_added_to_hass(self) -> None:
        """Restore the last state (default on)."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        self.coordinator.alerts_enabled = not (last is not None and last.state == STATE_OFF)

    @property
    def is_on(self) -> bool:
        """Return whether alerts are enabled."""
        return self.coordinator.alerts_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable alerts."""
        self.coordinator.alerts_enabled = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable alerts."""
        self.coordinator.alerts_enabled = False
        self.async_write_ha_state()
