"""Base entity for NHL Companion."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_TEAM_ABBREV, DOMAIN
from .coordinator import TeamCoordinator


def team_device_info(entry_id: str, abbrev: str, name: str) -> DeviceInfo:
    """One service device per followed team."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name=name,
        manufacturer="NHL",
        model=f"{abbrev} game tracker",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://www.nhl.com/schedule",
    )


class NhlTeamEntity(CoordinatorEntity[TeamCoordinator]):
    """Entity tied to one followed team."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TeamCoordinator, key: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        abbrev = entry.data[CONF_TEAM_ABBREV]
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = team_device_info(entry.entry_id, abbrev, entry.title)
        self.team_abbrev = abbrev
