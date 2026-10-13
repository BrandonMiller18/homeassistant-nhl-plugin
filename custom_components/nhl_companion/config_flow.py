"""Config flow for NHL Companion."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
import voluptuous as vol

from .api import NhlApiClient, NhlApiError
from .const import (
    CONF_ALERT_DELAY,
    CONF_API_BASE_URL,
    CONF_GAME_DAY_HOUR,
    CONF_GAME_SOON_MINUTES,
    CONF_LIVE_INTERVAL,
    CONF_TEAM_ABBREV,
    CONF_TEAM_NAME,
    CONF_TRACK_OPPONENT,
    DEFAULT_ALERT_DELAY,
    DEFAULT_API_BASE_URL,
    DEFAULT_GAME_DAY_HOUR,
    DEFAULT_GAME_SOON_MINUTES,
    DEFAULT_LIVE_INTERVAL,
    DEFAULT_TRACK_OPPONENT,
    DOMAIN,
    MAX_ALERT_DELAY,
    MIN_LIVE_INTERVAL,
    TEAMS,
)

_LOGGER = logging.getLogger(__name__)


class NhlCompanionConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pick a team to follow."""

    VERSION = 1

    async def _team_names(self) -> dict[str, str]:
        client = NhlApiClient(async_get_clientsession(self.hass), DEFAULT_API_BASE_URL)
        try:
            standings = await client.get_standings()
        except NhlApiError as err:
            _LOGGER.debug("Using built-in team list: %s", err)
            return dict(TEAMS)
        names = {s.abbrev: s.name for s in standings if s.abbrev}
        return dict(sorted(names.items(), key=lambda kv: kv[1])) or dict(TEAMS)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the team picker."""
        teams = await self._team_names()
        if user_input is not None:
            abbrev = user_input[CONF_TEAM_ABBREV]
            await self.async_set_unique_id(abbrev)
            self._abort_if_unique_id_configured()
            name = teams.get(abbrev, TEAMS.get(abbrev, abbrev))
            return self.async_create_entry(title=name, data={CONF_TEAM_ABBREV: abbrev, CONF_TEAM_NAME: name})

        configured = {e.unique_id for e in self._async_current_entries()}
        options = [
            SelectOptionDict(value=abbrev, label=f"{name} ({abbrev})")
            for abbrev, name in sorted(teams.items(), key=lambda kv: kv[1])
            if abbrev not in configured
        ]
        if not options:
            return self.async_abort(reason="all_configured")
        schema = vol.Schema(
            {
                vol.Required(CONF_TEAM_ABBREV): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return NhlCompanionOptionsFlow()


def _number(minimum: int, maximum: int, unit: str) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum, max=maximum, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement=unit
        )
    )


class NhlCompanionOptionsFlow(OptionsFlow):
    """Tune polling, delays and alerts."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show options."""
        if user_input is not None:
            data = dict(user_input)
            for key in (CONF_LIVE_INTERVAL, CONF_ALERT_DELAY, CONF_GAME_SOON_MINUTES, CONF_GAME_DAY_HOUR):
                data[key] = int(data[key])
            data[CONF_API_BASE_URL] = (data.get(CONF_API_BASE_URL) or DEFAULT_API_BASE_URL).strip()
            return self.async_create_entry(data=data)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LIVE_INTERVAL, default=opts.get(CONF_LIVE_INTERVAL, DEFAULT_LIVE_INTERVAL)
                ): _number(MIN_LIVE_INTERVAL, 120, "s"),
                vol.Required(
                    CONF_ALERT_DELAY, default=opts.get(CONF_ALERT_DELAY, DEFAULT_ALERT_DELAY)
                ): _number(0, MAX_ALERT_DELAY, "s"),
                vol.Required(
                    CONF_GAME_SOON_MINUTES,
                    default=opts.get(CONF_GAME_SOON_MINUTES, DEFAULT_GAME_SOON_MINUTES),
                ): _number(1, 240, "min"),
                vol.Required(
                    CONF_GAME_DAY_HOUR, default=opts.get(CONF_GAME_DAY_HOUR, DEFAULT_GAME_DAY_HOUR)
                ): _number(0, 23, "h"),
                vol.Required(
                    CONF_TRACK_OPPONENT,
                    default=opts.get(CONF_TRACK_OPPONENT, DEFAULT_TRACK_OPPONENT),
                ): BooleanSelector(),
                vol.Optional(
                    CONF_API_BASE_URL,
                    default=opts.get(CONF_API_BASE_URL, DEFAULT_API_BASE_URL),
                ): TextSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
