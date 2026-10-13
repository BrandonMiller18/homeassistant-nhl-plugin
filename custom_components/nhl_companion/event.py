"""Event entities: goal, penalty, period and game."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NhlConfigEntry
from .const import GAME_EVENTS, GOAL_EVENTS, PENALTY_EVENTS, PERIOD_EVENTS, SIGNAL_EVENT
from .coordinator import TeamCoordinator
from .entity import NhlTeamEntity

EVENT_GROUPS: dict[str, list[str]] = {
    "goal": GOAL_EVENTS,
    "penalty": PENALTY_EVENTS,
    "period": PERIOD_EVENTS,
    "game": GAME_EVENTS,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NhlConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up event entities."""
    team = entry.runtime_data.team
    async_add_entities(NhlEventEntity(team, group, types) for group, types in EVENT_GROUPS.items())


class NhlEventEntity(NhlTeamEntity, EventEntity):
    """Fires when the integration emits an event in its group.

    The last payload stays in the attributes, so dashboards can show the
    last goal scorer and assists.
    """

    def __init__(self, coordinator: TeamCoordinator, group: str, types: list[str]) -> None:
        """Initialize."""
        super().__init__(coordinator, f"{group}_event")
        self._attr_event_types = list(types)

    async def async_added_to_hass(self) -> None:
        """Listen for events from the coordinator."""
        await super().async_added_to_hass()
        signal = SIGNAL_EVENT.format(entry_id=self.coordinator.config_entry.entry_id)
        self.async_on_remove(async_dispatcher_connect(self.hass, signal, self._handle_event))

    @callback
    def _handle_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if event_type not in self._attr_event_types:
            return
        attributes = {k: v for k, v in payload.items() if k != "type"}
        self._trigger_event(event_type, attributes)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """State only changes when an event fires."""
