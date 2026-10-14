"""Async client for the public NHL web API (api-web.nhle.com)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from .const import (
    BRIGHTCOVE_ACCOUNT,
    BRIGHTCOVE_PLAYBACK_URL,
    BRIGHTCOVE_PLAYER_CONFIG_URL,
    DEFAULT_API_BASE_URL,
    VERSION,
)
from .models import Clip, Game, GameSnapshot, ScheduleDay, Standing
from .parser import (
    parse_clip,
    parse_club_schedule,
    parse_play_by_play,
    parse_schedule,
    parse_standings,
    parse_three_stars,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)
# Two config entries following the same game share one fetch inside this window
CACHE_SECONDS = 4.0
# Bodies kept for conditional requests (one per URL; old games fall out)
MAX_ETAGS = 16


def _cache_expiry(headers: Any, received: float) -> float | None:
    """Monotonic time the CDN copy we just got goes stale, from Cache-Control and Age.

    Live play-by-play is served by Cloudflare with max-age=19 and is rebuilt every
    20 s, so this tells the coordinator when a new copy can first exist.
    """
    max_age = None
    for part in (headers.get("Cache-Control") or "").split(","):
        name, _, value = part.strip().partition("=")
        if name == "max-age" and value.isdigit():
            max_age = int(value)
    if max_age is None:
        return None
    try:
        age = int(headers.get("Age") or 0)
    except ValueError:
        age = 0
    return received + max(0, max_age - age)


class NhlApiError(Exception):
    """The NHL API returned an error or unusable data."""


class NhlConnectionError(NhlApiError):
    """The NHL API could not be reached."""


class NhlAuthError(NhlApiError):
    """A video service rejected the request (stale policy key)."""


class NhlApiClient:
    """Thin async wrapper around the endpoints this integration uses."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str = DEFAULT_API_BASE_URL) -> None:
        """Initialize the client."""
        self._session = session
        self.base_url = base_url.rstrip("/")
        self._cache: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        # url -> (ETag, body) for conditional requests; the API answers 304 on a match
        self._etags: dict[str, tuple[str, dict[str, Any]]] = {}
        self._expires: dict[str, float] = {}
        self._policy_key: str | None = None

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def seconds_until_stale(self, path: str) -> float | None:
        """Seconds until the last response for path expires at the CDN, if known."""
        expires = self._expires.get(self._url(path))
        if expires is None:
            return None
        return max(0.0, expires - time.monotonic())

    async def _get(self, path: str, cache: bool = True) -> dict[str, Any]:
        url = self._url(path)
        lock = self._locks.setdefault(url, asyncio.Lock())
        async with lock:
            if cache and (hit := self._cache.get(url)) and time.monotonic() - hit[0] < CACHE_SECONDS:
                return hit[1]
            headers = {"User-Agent": f"HomeAssistant-NHLCompanion/{VERSION}"}
            known = self._etags.get(url)
            if known:
                headers["If-None-Match"] = known[0]
            try:
                async with self._session.get(url, timeout=REQUEST_TIMEOUT, headers=headers) as resp:
                    if resp.status == 404:
                        raise NhlApiError(f"Not found: {url}")
                    if resp.status >= 400:
                        raise NhlConnectionError(f"HTTP {resp.status} from {url}")
                    if (expires := _cache_expiry(resp.headers, time.monotonic())) is not None:
                        self._expires[url] = expires
                    if resp.status == 304 and known:
                        data = known[1]
                    else:
                        data = await resp.json(content_type=None)
                        if isinstance(data, dict) and (etag := resp.headers.get("ETag")):
                            self._etags.pop(url, None)
                            self._etags[url] = (etag, data)
                            while len(self._etags) > MAX_ETAGS:
                                self._etags.pop(next(iter(self._etags)))
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

    async def get_three_stars(self, game_id: int) -> list[dict[str, Any]]:
        """Three stars of a game; empty until shortly after the final."""
        return parse_three_stars(await self._get(f"gamecenter/{game_id}/landing", cache=False))

    async def get_clip(self, clip_id: int | str) -> Clip:
        """Resolve an NHL video clip id to playable stream URLs.

        NHL clips are hosted on Brightcove. The Playback API needs the policy key
        from the NHL's public player config; it is fetched once and refreshed if
        Brightcove rejects it. Stream URLs are signed, so resolve them when needed.
        """
        for attempt in range(2):
            if self._policy_key is None or attempt:
                config = await self._get_json(BRIGHTCOVE_PLAYER_CONFIG_URL)
                self._policy_key = (config.get("video_cloud") or {}).get("policy_key")
                if not self._policy_key:
                    raise NhlApiError("No Brightcove policy key in the NHL player config")
            url = BRIGHTCOVE_PLAYBACK_URL.format(account=BRIGHTCOVE_ACCOUNT, video_id=clip_id)
            try:
                data = await self._get_json(url, {"Accept": f"application/json;pk={self._policy_key}"})
            except NhlAuthError:
                if attempt:
                    raise
                continue
            clip = parse_clip(data)
            if clip.mp4 is None and clip.hls is None:
                raise NhlApiError(f"Clip {clip_id} has no playable stream")
            return clip
        raise NhlApiError(f"Clip {clip_id} unavailable")

    async def _get_json(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        """GET an absolute URL outside the NHL API (no caching)."""
        try:
            async with self._session.get(url, timeout=REQUEST_TIMEOUT, headers=headers or {}) as resp:
                if resp.status in (401, 403):
                    raise NhlAuthError(f"HTTP {resp.status} from {url}")
                if resp.status == 404:
                    raise NhlApiError(f"Not found: {url}")
                if resp.status >= 400:
                    raise NhlConnectionError(f"HTTP {resp.status} from {url}")
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise NhlConnectionError(f"Error requesting {url}: {err}") from err
        if not isinstance(data, dict):
            raise NhlApiError(f"Unexpected response from {url}")
        return data

    async def get_raw(self, path: str) -> dict[str, Any]:
        """Fetch raw JSON (diagnostics and fixture recording)."""
        return await self._get(path, cache=False)
