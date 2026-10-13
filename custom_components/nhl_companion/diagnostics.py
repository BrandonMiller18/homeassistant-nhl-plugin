"""Diagnostics for NHL Companion."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import NhlConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: NhlConfigEntry) -> dict[str, Any]:
    """Return coordinator state for bug reports. Contains no secrets."""
    team = entry.runtime_data.team
    data = team.data
    state = team.detector.state
    return {
        "entry": {"data": dict(entry.data), "options": dict(entry.options)},
        "alerts_enabled": team.alerts_enabled,
        "update_interval": str(team.update_interval),
        "current_game": data.current_game.as_dict() if data and data.current_game else None,
        "next_game": data.next_game.as_dict() if data and data.next_game else None,
        "strength": data.strength if data else None,
        "play_count": len(data.snapshot.plays) if data and data.snapshot else None,
        "detector": state.as_dict() if state else None,
        "last_events": data.last_events if data else {},
    }
