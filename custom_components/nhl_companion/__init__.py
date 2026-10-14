"""The NHL Companion integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .api import NhlApiClient, NhlApiError
from .const import ALL_EVENTS, CONF_API_BASE_URL, DEFAULT_API_BASE_URL, DOMAIN, EVT_GOAL_HIGHLIGHT
from .coordinator import STORAGE_VERSION, LeagueCoordinator, TeamCoordinator
from .frontend import async_register_frontend
from .websocket_api import async_register_websocket

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SIMULATE = "simulate_event"
SERVICE_REFRESH = "refresh"
SERVICE_PLAY_HIGHLIGHT = "play_highlight"
ATTR_CLIP_ID = "clip_id"
ATTR_FORMAT = "format"
CONTENT_TYPES = {"mp4": "video/mp4", "hls": "application/x-mpegURL"}
ATTR_ENTRY = "config_entry_id"
ATTR_TYPE = "type"
ATTR_SCORER = "scorer_name"

SIMULATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TYPE): vol.In(ALL_EVENTS),
        vol.Optional(ATTR_ENTRY): cv.string,
        vol.Optional(ATTR_SCORER): cv.string,
    }
)
REFRESH_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTRY): cv.string})
PLAY_HIGHLIGHT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Optional(ATTR_ENTRY): cv.string,
        vol.Optional(ATTR_CLIP_ID): vol.All(cv.string, vol.Match(r"^\d+$")),
        vol.Optional(ATTR_FORMAT, default="mp4"): vol.In(list(CONTENT_TYPES)),
    }
)


@dataclass
class NhlRuntimeData:
    """Objects owned by one config entry."""

    client: NhlApiClient
    league: LeagueCoordinator
    team: TeamCoordinator


type NhlConfigEntry = ConfigEntry[NhlRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up domain-level pieces: cards, websocket commands, services."""
    hass.data.setdefault(DOMAIN, {"clients": {}, "leagues": {}})
    await async_register_frontend(hass)
    async_register_websocket(hass)
    _register_services(hass)
    return True


def _shared_client(hass: HomeAssistant, base_url: str) -> NhlApiClient:
    clients: dict[str, NhlApiClient] = hass.data[DOMAIN]["clients"]
    if base_url not in clients:
        clients[base_url] = NhlApiClient(async_get_clientsession(hass), base_url)
    return clients[base_url]


async def async_setup_entry(hass: HomeAssistant, entry: NhlConfigEntry) -> bool:
    """Set up one followed team."""
    hass.data.setdefault(DOMAIN, {"clients": {}, "leagues": {}})
    base_url = entry.options.get(CONF_API_BASE_URL) or DEFAULT_API_BASE_URL
    client = _shared_client(hass, base_url)

    leagues: dict[str, LeagueCoordinator] = hass.data[DOMAIN]["leagues"]
    league = leagues.get(base_url)
    if league is None:
        league = LeagueCoordinator(hass, client)
        leagues[base_url] = league
        await league.async_refresh()
    league.users += 1

    team = TeamCoordinator(hass, entry, client)
    try:
        await team.async_config_entry_first_refresh()
    except Exception:
        _release_league(hass, base_url)
        raise

    entry.runtime_data = NhlRuntimeData(client=client, league=league, team=team)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: NhlConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def _release_league(hass: HomeAssistant, base_url: str) -> None:
    leagues: dict[str, LeagueCoordinator] = hass.data[DOMAIN]["leagues"]
    league = leagues.get(base_url)
    if league is None:
        return
    league.users -= 1
    if league.users <= 0:
        leagues.pop(base_url)
        hass.async_create_task(league.async_shutdown())


async def async_unload_entry(hass: HomeAssistant, entry: NhlConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        _release_league(hass, entry.runtime_data.client.base_url)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: NhlConfigEntry) -> None:
    """Delete persisted detector state."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


def _target_entries(hass: HomeAssistant, call: ServiceCall) -> list[NhlConfigEntry]:
    entries = [e for e in hass.config_entries.async_loaded_entries(DOMAIN)]
    if entry_id := call.data.get(ATTR_ENTRY):
        entries = [e for e in entries if e.entry_id == entry_id]
        if not entries:
            raise ServiceValidationError(f"No loaded NHL Companion entry {entry_id}")
    return entries


@callback
def _register_services(hass: HomeAssistant) -> None:
    async def simulate(call: ServiceCall) -> None:
        overrides = {}
        if scorer := call.data.get(ATTR_SCORER):
            first, _, last = scorer.partition(" ")
            overrides["scorer"] = {
                "id": 0,
                "name": scorer,
                "first_name": first,
                "last_name": last,
                "number": None,
                "position": None,
                "headshot": None,
                "season_total": None,
            }
        for entry in _target_entries(hass, call):
            entry.runtime_data.team.async_simulate(call.data[ATTR_TYPE], overrides)

    async def refresh(call: ServiceCall) -> None:
        for entry in _target_entries(hass, call):
            await entry.runtime_data.team.async_request_refresh()
            await entry.runtime_data.league.async_request_refresh()

    async def play_highlight(call: ServiceCall) -> ServiceResponse:
        entries = _target_entries(hass, call)
        if not entries:
            raise ServiceValidationError("NHL Companion is not set up")
        goal: dict | None = None
        clip_id = call.data.get(ATTR_CLIP_ID)
        if clip_id is None:
            # Latest goal video any of the target teams saw
            for entry in entries:
                last = entry.runtime_data.team.data.last_events.get(EVT_GOAL_HIGHLIGHT)
                if last and (goal is None or last.get("fired_at", "") > goal.get("fired_at", "")):
                    goal = last
            if goal is None:
                raise ServiceValidationError("No goal video has been posted yet; pass clip_id")
            clip_id = goal["clip_id"]
        try:
            clip = await entries[0].runtime_data.client.get_clip(clip_id)
        except NhlApiError as err:
            raise HomeAssistantError(f"Could not load NHL clip {clip_id}: {err}") from err
        fmt = call.data[ATTR_FORMAT]
        url = clip.mp4 if fmt == "mp4" else clip.hls
        if url is None:
            fmt = "hls" if fmt == "mp4" else "mp4"
            url = clip.mp4 if fmt == "mp4" else clip.hls
        if targets := call.data.get(ATTR_ENTITY_ID):
            await hass.services.async_call(
                "media_player",
                "play_media",
                {
                    ATTR_ENTITY_ID: targets,
                    "media_content_id": url,
                    "media_content_type": CONTENT_TYPES[fmt],
                    "extra": {"title": clip.title, "thumb": clip.poster},
                },
                blocking=True,
                context=call.context,
            )
        return {**clip.as_dict(), "url": url, "format": fmt, "goal": goal}

    hass.services.async_register(DOMAIN, SERVICE_SIMULATE, simulate, schema=SIMULATE_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_PLAY_HIGHLIGHT,
        play_highlight,
        schema=PLAY_HIGHLIGHT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, refresh, schema=REFRESH_SCHEMA)
