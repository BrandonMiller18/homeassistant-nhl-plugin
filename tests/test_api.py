"""API client caching against the headers the real NHL CDN sends."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.nhl_companion import api as api_mod
from custom_components.nhl_companion.api import NhlApiClient, _cache_expiry

BASE = "https://api.test/v1"
URL = f"{BASE}/gamecenter/1/play-by-play"
# Headers as recorded from api-web.nhle.com during a live game
LIVE_HEADERS = {
    "Cache-Control": "no-transform, max-age=19, s-maxage=19",
    "Age": "7",
    "ETag": 'W/"6acecac4--gzip"',
}


def test_cache_expiry_from_max_age_and_age() -> None:
    assert _cache_expiry(LIVE_HEADERS, 100.0) == 112.0
    assert _cache_expiry({"Cache-Control": "max-age=19", "Age": "30"}, 100.0) == 100.0
    assert _cache_expiry({"Cache-Control": "max-age=19"}, 100.0) == 119.0
    assert _cache_expiry({}, 100.0) is None


async def test_conditional_request_reuses_body_on_304(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, monkeypatch
) -> None:
    monkeypatch.setattr(api_mod, "CACHE_SECONDS", 0)
    session = aioclient_mock.create_session(hass.loop)
    client = NhlApiClient(session, BASE)

    aioclient_mock.get(URL, json={"id": 1, "plays": []}, headers=LIVE_HEADERS)
    first = await client.get_raw("gamecenter/1/play-by-play")
    assert 11 <= client.seconds_until_stale("gamecenter/1/play-by-play") <= 12

    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, status=304, headers={**LIVE_HEADERS, "Age": "17"})
    second = await client.get_raw("gamecenter/1/play-by-play")

    assert second == first
    sent = aioclient_mock.mock_calls[0][3]
    assert sent["If-None-Match"] == LIVE_HEADERS["ETag"]
    assert client.seconds_until_stale("gamecenter/1/play-by-play") <= 2
    assert client.seconds_until_stale("standings/now") is None
    await session.close()
