"""Async client for the public NHL web API (api-web.nhle.com)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from .const import DEFAULT_API_BASE_URL, VERSION
from .models import Game, GameSnapshot, ScheduleDay, Standing
from .parser import (
    parse_club_schedule,
    parse_play_by_play,
    parse_schedule,
    parse_standings,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)
# Two config entries following the same game share one fetch inside this window
CACHE_SECONDS = 4.0


class NhlApiError(Exception):
    """The NHL API returned an error or unusable data."""


class NhlConnectionError(NhlApiError):
    """The NHL API could not be reached."""


class NhlApiClient:
    """Thin async wrapper around the endpoints this integration uses."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str = DEFAULT_API_BASE_URL) -> None:
        """Initialize the client."""
        self._session = session
        self.base_url = base_url.rstrip("/")
        self._cache: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def _get(self, path: str, cache: bool = True) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        lock = self._locks.setdefault(url, asyncio.Lock())
        async with lock:
            if cache and (hit := self._cache.get(url)) and time.monotonic() - hit[0] < CACHE_SECONDS:
                return hit[1]
            try:
                async with self._session.get(
                    url,
                    timeout=REQUEST_TIMEOUT,
                    headers={"User-Agent": f"HomeAssistant-NHLCompanion/{VERSION}"},
                ) as resp:
                    if resp.status == 404:
                        raise NhlApiError(f"Not found: {url}")
                    if resp.status >= 400:
                        raise NhlConnectionError(f"HTTP {resp.status} from {url}")
                    data = await resp.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError) as err:
                raise NhlConnectionError(f"Error requesting {url}: {err}") from err
            if not isinstance(data, dict):
                raise NhlApiError(f"Unexpected response from {url}")
            self._cache[url] = (time.monotonic(), data)
            return data

    async def get_schedule(self, date: str | None = None) -> list[ScheduleDay]:
        """League schedule for the week containing date (default today)."""
        return parse_schedule(await self._get(f"schedule/{date or 'now'}"))

    async def get_standings(self) -> list[Standing]:
        """Current league standings."""
        return parse_standings(await self._get("standings/now"))

    async def get_team_schedule(self, team_abbrev: str) -> list[Game]:
        """A team's full season schedule."""
        return parse_club_schedule(await self._get(f"club-schedule-season/{team_abbrev}/now"))

    async def get_play_by_play(self, game_id: int) -> GameSnapshot:
        """Live play-by-play for a game."""
        return parse_play_by_play(await self._get(f"gamecenter/{game_id}/play-by-play"))

    async def get_raw(self, path: str) -> dict[str, Any]:
        """Fetch raw JSON (diagnostics and fixture recording)."""
        return await self._get(path, cache=False)
