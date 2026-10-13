"""Config and options flow tests."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nhl_companion.api import NhlConnectionError
from custom_components.nhl_companion.const import (
    CONF_ALERT_DELAY,
    CONF_API_BASE_URL,
    CONF_LIVE_INTERVAL,
    CONF_TEAM_ABBREV,
    DOMAIN,
)


async def test_user_flow_creates_entry(hass: HomeAssistant, mock_api) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.nhl_companion.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_TEAM_ABBREV: "BOS"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Boston Bruins"
    assert result["data"][CONF_TEAM_ABBREV] == "BOS"


async def test_user_flow_falls_back_to_builtin_teams(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.nhl_companion.api.NhlApiClient.get_standings",
        side_effect=NhlConnectionError("offline"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        with patch("custom_components.nhl_companion.async_setup_entry", return_value=True):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_TEAM_ABBREV: "WPG"}
            )
    assert result["title"] == "Winnipeg Jets"


async def test_configured_team_is_hidden(hass: HomeAssistant, mock_api) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="BOS", data={CONF_TEAM_ABBREV: "BOS"}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    selector = result["data_schema"].schema[CONF_TEAM_ABBREV]
    offered = [o["value"] for o in selector.config["options"]]
    assert "BOS" not in offered
    assert "TOR" in offered


async def test_options_flow(hass: HomeAssistant, mock_api) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="BOS", title="Boston Bruins", data={CONF_TEAM_ABBREV: "BOS"}
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_LIVE_INTERVAL: 7,
            CONF_ALERT_DELAY: 30,
            "game_soon_minutes": 45,
            "game_day_hour": 10,
            "track_opponent": False,
            CONF_API_BASE_URL: "",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_LIVE_INTERVAL] == 7
    assert entry.options[CONF_ALERT_DELAY] == 30
    assert entry.options[CONF_API_BASE_URL] == "https://api-web.nhle.com/v1"
