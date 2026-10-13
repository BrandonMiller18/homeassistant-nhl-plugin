"""Websocket commands used by the bundled cards."""

from __future__ import annotations

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
import voluptuous as vol

from .api import NhlApiError
from .const import CONF_TEAM_ABBREV, DOMAIN
from .coordinator import LeagueCoordinator


def _league(hass: HomeAssistant) -> LeagueCoordinator | None:
    leagues: dict[str, LeagueCoordinator] = hass.data.get(DOMAIN, {}).get("leagues", {})
    return next(iter(leagues.values()), None)


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Register commands."""
    websocket_api.async_register_command(hass, ws_schedule)
    websocket_api.async_register_command(hass, ws_standings)
    websocket_api.async_register_command(hass, ws_teams)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/schedule",
        vol.Optional("date"): vol.Match(r"^\d{4}-\d{2}-\d{2}$"),
    }
)
@websocket_api.async_response
async def ws_schedule(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the league schedule week (cached unless a date is given)."""
    league = _league(hass)
    if league is None:
        connection.send_error(msg["id"], "not_loaded", "NHL Companion is not set up")
        return
    if date := msg.get("date"):
        try:
            days = await league.client.get_schedule(date)
        except NhlApiError as err:
            connection.send_error(msg["id"], "api_error", str(err))
            return
    else:
        days = league.data.schedule if league.data else []
    connection.send_result(msg["id"], {"days": [d.as_dict() for d in days]})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/standings"})
@callback
def ws_standings(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return current standings."""
    league = _league(hass)
    if league is None:
        connection.send_error(msg["id"], "not_loaded", "NHL Companion is not set up")
        return
    rows = league.data.standings if league.data else []
    connection.send_result(msg["id"], {"standings": [s.as_dict() for s in rows]})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/teams"})
@callback
def ws_teams(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Return the followed teams (for card editors and highlighting)."""
    teams = [
        {"entry_id": e.entry_id, "abbrev": e.data[CONF_TEAM_ABBREV], "name": e.title}
        for e in hass.config_entries.async_entries(DOMAIN)
    ]
    connection.send_result(msg["id"], {"teams": teams})
