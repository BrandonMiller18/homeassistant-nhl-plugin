"""Integration setup, entities, events, services and toggle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from fake_nhl import FakeGame
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.nhl_companion.const import (
    CONF_ALERT_DELAY,
    CONF_TEAM_ABBREV,
    CONF_TRACK_OPPONENT,
    DOMAIN,
    EVENT_NHL,
)
from custom_components.nhl_companion.models import Clip

PASTA, MCAVOY, MATTHEWS = 8477956, 8479325, 8479318


async def setup_entry(hass: HomeAssistant, options: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="BOS",
        title="Boston Bruins",
        data={CONF_TEAM_ABBREV: "BOS", "team_name": "Boston Bruins"},
        options=options or {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def entity_id(hass: HomeAssistant, entry: MockConfigEntry, domain: str, key: str) -> str:
    registry = er.async_get(hass)
    eid = registry.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
    assert eid, f"missing {domain} {key}"
    return eid


async def advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: int = 3700) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_setup_creates_entities(hass: HomeAssistant, mock_api) -> None:
    entry = await setup_entry(hass)
    assert entry.state is ConfigEntryState.LOADED

    status = hass.states.get(entity_id(hass, entry, "sensor", "game_status"))
    assert status.state == "scheduled"
    assert status.attributes["opponent_abbrev"] == "TOR"
    assert status.attributes["is_home"] is True

    nxt = hass.states.get(entity_id(hass, entry, "sensor", "next_game"))
    assert nxt.state != "unknown"
    assert nxt.attributes["matchup"] == "vs TOR"

    standing = hass.states.get(entity_id(hass, entry, "sensor", "standing"))
    assert standing.state == "41"
    assert standing.attributes["record"] == "19-6-3"

    assert hass.states.get(entity_id(hass, entry, "switch", "game_alerts")).state == "on"
    assert hass.states.get(entity_id(hass, entry, "binary_sensor", "game_live")).state == "off"
    for group in ("goal", "penalty", "period", "game"):
        entity_id(hass, entry, "event", f"{group}_event")

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_live_game_fires_events(
    hass: HomeAssistant, mock_api, fake_game: FakeGame, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime(2025, 11, 1, 23, 0, tzinfo=UTC))
    fake_game.start = datetime(2025, 11, 1, 23, 5, tzinfo=UTC)
    fake_game.pregame()
    entry = await setup_entry(hass)
    events = async_capture_events(hass, EVENT_NHL)

    fake_game.start_period(1)
    await advance(hass, freezer, 60)
    fake_game.goal("BOS", PASTA, MCAVOY, time_in_period="03:21")
    await advance(hass, freezer, 15)

    fired = [e.data["type"] for e in events]
    assert "game_start" in fired
    assert "period_start" in fired
    goal = next(e.data for e in events if e.data["type"] == "team_goal")
    assert goal["scorer"]["name"] == "David Pastrnak"
    assert goal["config_entry_id"] == entry.entry_id

    goal_entity = hass.states.get(entity_id(hass, entry, "event", "goal_event"))
    assert goal_entity.attributes["event_type"] == "team_goal"
    assert goal_entity.attributes["scorer"]["name"] == "David Pastrnak"

    status = hass.states.get(entity_id(hass, entry, "sensor", "game_status"))
    assert status.state == "live"
    assert hass.states.get(entity_id(hass, entry, "sensor", "team_score")).state == "1"
    assert status.attributes["last_goal"]["scorer"]["name"] == "David Pastrnak"
    assert hass.states.get(entity_id(hass, entry, "binary_sensor", "game_live")).state == "on"

    # Alerts off: a goal is not announced, but the score still updates
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": entity_id(hass, entry, "switch", "game_alerts")}, blocking=True
    )
    count = len(events)
    fake_game.goal("BOS", PASTA)
    await advance(hass, freezer, 15)
    assert len(events) == count
    assert hass.states.get(entity_id(hass, entry, "sensor", "team_score")).state == "2"

    # Back on: the suppressed goal is not replayed, new ones fire
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": entity_id(hass, entry, "switch", "game_alerts")}, blocking=True
    )
    await advance(hass, freezer, 15)
    assert len(events) == count
    fake_game.goal("TOR", MATTHEWS)
    fake_game.final()
    await advance(hass, freezer, 15)
    assert [e.data["type"] for e in events[count:]] == ["opponent_goal", "game_end_win"]


async def test_power_play_from_situation_block(
    hass: HomeAssistant, mock_api, fake_game: FakeGame, freezer: FrozenDateTimeFactory
) -> None:
    """The situation block flips power play on as soon as the penalty is posted."""
    freezer.move_to(datetime(2025, 11, 1, 23, 0, tzinfo=UTC))
    fake_game.start = datetime(2025, 11, 1, 23, 5, tzinfo=UTC)
    fake_game.start_period(1)
    entry = await setup_entry(hass)
    pp = entity_id(hass, entry, "binary_sensor", "power_play")
    assert hass.states.get(pp).state == "off"

    # Delayed penalty on TOR: BOS pulls its goalie for an extra attacker, not a power play
    fake_game.delayed_penalty("TOR")
    await advance(hass, freezer, 15)
    assert hass.states.get(pp).state == "off"

    # Penalty posted with the pre-penalty situationCode; the block already says PP
    fake_game.penalty("TOR", MATTHEWS, PASTA)
    fake_game.power_play("BOS", "02:00")
    await advance(hass, freezer, 15)
    state = hass.states.get(pp)
    assert state.state == "on"
    assert state.attributes["time_remaining"] == "02:00"
    status = hass.states.get(entity_id(hass, entry, "sensor", "game_status"))
    assert status.attributes["power_play_time_remaining"] == "02:00"

    fake_game.power_play("TOR", "01:30")
    await advance(hass, freezer, 15)
    assert hass.states.get(pp).attributes["strength"] == "sh"

    # Block gone and last play at even strength: back to even
    fake_game.power_play(None)
    fake_game.shot("BOS", PASTA)
    await advance(hass, freezer, 15)
    assert hass.states.get(pp).state == "off"
    assert hass.states.get(pp).attributes["strength"] == "ev"

    # Without the block, fall back to the last play's situationCode (home BOS 5 on 4)
    fake_game.goal("TOR", MATTHEWS, situation="1451")
    await advance(hass, freezer, 15)
    assert hass.states.get(pp).state == "on"
    assert hass.states.get(pp).attributes["time_remaining"] is None


async def test_goal_video_stats_and_three_stars(
    hass: HomeAssistant, mock_api, fake_game: FakeGame, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime(2025, 11, 1, 23, 0, tzinfo=UTC))
    fake_game.start = datetime(2025, 11, 1, 22, 30, tzinfo=UTC)
    fake_game.start_period(1)
    entry = await setup_entry(hass)
    events = async_capture_events(hass, EVENT_NHL)
    played = async_mock_service(hass, "media_player", "play_media")

    goal_id = fake_game.goal("BOS", PASTA, MCAVOY)
    fake_game.shot("TOR", MATTHEWS)
    await advance(hass, freezer, 15)
    assert hass.states.get(entity_id(hass, entry, "sensor", "team_shots")).state == "1"
    assert hass.states.get(entity_id(hass, entry, "sensor", "opponent_shots")).state == "1"
    status = hass.states.get(entity_id(hass, entry, "sensor", "game_status"))
    assert status.attributes["team_stats"]["shots_on_goal"] == 1
    assert status.attributes["goals"][0]["scorer"] == "David Pastrnak"

    # No video yet
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "play_highlight", {}, blocking=True, return_response=True)

    fake_game.amend(goal_id, highlightClip=6406806930112)
    await advance(hass, freezer, 15)
    highlight = next(e.data for e in events if e.data["type"] == "goal_highlight")
    assert highlight["clip_id"] == "6406806930112"
    assert highlight["clip_type"] == "full"
    status = hass.states.get(entity_id(hass, entry, "sensor", "game_status"))
    assert status.attributes["last_goal_video"]["clip_id"] == "6406806930112"

    clip = Clip("6406806930112", "Pastrnak scores", 42.4, "https://cdn/720.mp4", "https://cdn/x.m3u8", None)
    with patch("custom_components.nhl_companion.api.NhlApiClient.get_clip", return_value=clip) as get_clip:
        response = await hass.services.async_call(
            DOMAIN,
            "play_highlight",
            {"entity_id": "media_player.living_room_tv"},
            blocking=True,
            return_response=True,
        )
    get_clip.assert_awaited_once_with("6406806930112")
    assert response["url"] == "https://cdn/720.mp4"
    assert response["goal"]["scorer"]["name"] == "David Pastrnak"
    assert played[0].data["media_content_id"] == "https://cdn/720.mp4"
    assert played[0].data["media_content_type"] == "video/mp4"
    assert played[0].data["entity_id"] == ["media_player.living_room_tv"]

    # Three stars are empty right after the final and are retried until posted
    fake_game.final()
    await advance(hass, freezer, 15)
    status = hass.states.get(entity_id(hass, entry, "sensor", "game_status"))
    assert status.state == "final"
    assert status.attributes["three_stars"] is None
    assert status.attributes["team_stats"]["shots_on_goal"] == 1
    mock_api.three_stars = [{"star": 1, "name": "David Pastrnak", "team_abbrev": "BOS"}]
    for _ in range(3):
        await advance(hass, freezer, 125)
    status = hass.states.get(entity_id(hass, entry, "sensor", "game_status"))
    assert status.attributes["three_stars"][0]["name"] == "David Pastrnak"
    assert status.attributes["team_stats"]["shots_on_goal"] == 1


async def test_alert_delay_and_opponent_filter(
    hass: HomeAssistant, mock_api, fake_game: FakeGame, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime(2025, 11, 1, 23, 0, tzinfo=UTC))
    fake_game.start = datetime(2025, 11, 1, 22, 30, tzinfo=UTC)
    fake_game.start_period(1)
    await setup_entry(hass, {CONF_ALERT_DELAY: 30, CONF_TRACK_OPPONENT: False})
    events = async_capture_events(hass, EVENT_NHL)

    fake_game.goal("TOR", MATTHEWS)
    fake_game.goal("BOS", PASTA)
    await advance(hass, freezer, 15)
    assert events == []
    await advance(hass, freezer, 31)
    assert [e.data["type"] for e in events] == ["team_goal"]


async def test_game_soon_and_game_day(
    hass: HomeAssistant, mock_api, fake_game: FakeGame, freezer: FrozenDateTimeFactory
) -> None:
    await hass.config.async_set_time_zone("America/New_York")
    # 7:00 PM local game; it's 6:45 PM local
    freezer.move_to(datetime(2025, 11, 1, 22, 45, tzinfo=UTC))
    fake_game.start = datetime(2025, 11, 1, 23, 0, tzinfo=UTC)
    events = async_capture_events(hass, EVENT_NHL)
    await setup_entry(hass)
    fired = [e.data["type"] for e in events]
    assert fired == ["game_day", "game_soon"]
    assert events[1].data["minutes_until_start"] == 15
    assert events[1].data["start_time_local"] == "7:00 PM"
    await advance(hass, freezer, 60)
    assert len(events) == 2


@pytest.mark.parametrize("evt_type", ["team_goal", "team_penalty", "game_end_win", "game_soon"])
async def test_simulate_service(hass: HomeAssistant, mock_api, evt_type: str) -> None:
    entry = await setup_entry(hass)
    events = async_capture_events(hass, EVENT_NHL)
    await hass.services.async_call(
        DOMAIN, "simulate_event", {"type": evt_type, "scorer_name": "Bobby Orr"}, blocking=True
    )
    assert len(events) == 1
    data = events[0].data
    assert data["type"] == evt_type
    assert data["simulated"] is True
    assert data["opponent_abbrev"] == "TOR"
    assert data["config_entry_id"] == entry.entry_id
    if evt_type == "team_goal":
        assert data["scorer"]["name"] == "Bobby Orr"
    if evt_type == "game_soon":
        assert data["start_time_local"]
        assert data["minutes_until_start"] >= 0


async def test_simulate_respects_toggle(hass: HomeAssistant, mock_api) -> None:
    entry = await setup_entry(hass)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": entity_id(hass, entry, "switch", "game_alerts")}, blocking=True
    )
    events = async_capture_events(hass, EVENT_NHL)
    await hass.services.async_call(DOMAIN, "simulate_event", {"type": "team_goal"}, blocking=True)
    assert events == []


async def test_websocket_commands(hass: HomeAssistant, hass_ws_client, mock_api) -> None:
    await setup_entry(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/standings"})
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"]["standings"][0]["abbrev"] == "BOS"

    await client.send_json_auto_id({"type": f"{DOMAIN}/schedule"})
    msg = await client.receive_json()
    assert msg["success"]
    assert len(msg["result"]["days"]) == 7

    await client.send_json_auto_id({"type": f"{DOMAIN}/teams"})
    msg = await client.receive_json()
    assert msg["result"]["teams"] == [
        {
            "entry_id": hass.config_entries.async_entries(DOMAIN)[0].entry_id,
            "abbrev": "BOS",
            "name": "Boston Bruins",
        }
    ]
