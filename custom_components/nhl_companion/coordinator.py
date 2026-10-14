"""Data update coordinators for NHL Companion."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import partial
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HassJob, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import NhlApiClient, NhlApiError
from .const import (
    CDN_REFRESH_SLACK,
    CONF_ALERT_DELAY,
    CONF_GAME_DAY_HOUR,
    CONF_GAME_SOON_MINUTES,
    CONF_LIVE_INTERVAL,
    CONF_TEAM_ABBREV,
    CONF_TRACK_OPPONENT,
    DEFAULT_ALERT_DELAY,
    DEFAULT_GAME_DAY_HOUR,
    DEFAULT_GAME_SOON_MINUTES,
    DEFAULT_LIVE_INTERVAL,
    DEFAULT_TRACK_OPPONENT,
    DOMAIN,
    EVENT_NHL,
    EVT_GAME_DAY,
    EVT_GAME_SOON,
    EVT_GOAL_UPDATED,
    FINISHED_STATES,
    INTERVAL_GAME_DAY,
    INTERVAL_IDLE,
    INTERVAL_LEAGUE_IDLE,
    INTERVAL_LEAGUE_LIVE,
    INTERVAL_PRE_GAME,
    LIVE_STATES,
    MIN_ALIGNED_POLL,
    MIN_LIVE_INTERVAL,
    OPPONENT_EVENTS,
    PBP_LEAD_MINUTES,
    SCHEDULE_REFRESH_SECONDS,
    SIGNAL_EVENT,
    STANDINGS_REFRESH_SECONDS,
    STATE_PRE,
    UPCOMING_STATES,
)
from .event_detector import DetectorState, EventDetector, period_label, strength_for
from .models import Game, GameSnapshot, NhlEvent, ScheduleDay, Standing

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
MAX_EMITTED_KEYS = 200
# Keep polling play-by-play this long after the scheduled start at most
MAX_GAME_HOURS = 8


def _clock_time(value: datetime) -> str:
    """7:00 PM style time without platform-specific strftime flags."""
    return f"{value.hour % 12 or 12}:{value.minute:02d} {'AM' if value.hour < 12 else 'PM'}"


@dataclass
class LeagueData:
    """League-wide schedule and standings."""

    schedule: list[ScheduleDay] = field(default_factory=list)
    standings: list[Standing] = field(default_factory=list)

    def standing_for(self, abbrev: str) -> Standing | None:
        """Find a team's standings row."""
        return next((s for s in self.standings if s.abbrev == abbrev), None)


class LeagueCoordinator(DataUpdateCoordinator[LeagueData]):
    """Shared schedule and standings, one per API base URL."""

    def __init__(self, hass: HomeAssistant, client: NhlApiClient) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=None,
            name=f"{DOMAIN}_league",
            update_interval=timedelta(seconds=INTERVAL_LEAGUE_IDLE),
        )
        self.client = client
        self._standings_fetched: datetime | None = None
        self.users = 0

    async def _async_update_data(self) -> LeagueData:
        previous = self.data or LeagueData()
        now = dt_util.utcnow()
        try:
            schedule = await self.client.get_schedule()
        except NhlApiError as err:
            if not previous.schedule:
                raise UpdateFailed(f"Schedule unavailable: {err}") from err
            _LOGGER.warning("Keeping cached schedule: %s", err)
            schedule = previous.schedule

        standings = previous.standings
        if (
            not standings
            or self._standings_fetched is None
            or (now - self._standings_fetched).total_seconds() > STANDINGS_REFRESH_SECONDS
        ):
            try:
                standings = await self.client.get_standings()
                self._standings_fetched = now
            except NhlApiError as err:
                _LOGGER.warning("Standings unavailable: %s", err)

        today = schedule[0].games if schedule else []
        busy = any(g.state in LIVE_STATES | {STATE_PRE} for g in today)
        self.update_interval = timedelta(seconds=INTERVAL_LEAGUE_LIVE if busy else INTERVAL_LEAGUE_IDLE)
        return LeagueData(schedule=schedule, standings=standings)


@dataclass
class TeamData:
    """Everything known about one followed team."""

    games: list[Game] = field(default_factory=list)
    current_game: Game | None = None
    next_game: Game | None = None
    last_game: Game | None = None
    snapshot: GameSnapshot | None = None
    strength: str | None = None
    power_play_remaining: str | None = None
    last_events: dict[str, dict[str, Any]] = field(default_factory=dict)


class TeamCoordinator(DataUpdateCoordinator[TeamData]):
    """Tracks one team's schedule and live game, and emits events."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: NhlApiClient) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.data[CONF_TEAM_ABBREV]}",
            update_interval=timedelta(seconds=INTERVAL_IDLE),
        )
        self.client = client
        self.team_abbrev: str = entry.data[CONF_TEAM_ABBREV]
        self.alerts_enabled = True
        self.detector = EventDetector(self.team_abbrev)
        self._emitted: list[str] = []
        self._schedule_fetched: datetime | None = None
        self._schedule_dirty = False
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._loaded = False

    # Options -------------------------------------------------------------

    def _opt(self, key: str, default: Any) -> Any:
        return self.config_entry.options.get(key, default)

    @property
    def live_interval(self) -> int:
        """Seconds between polls during a live game."""
        return max(MIN_LIVE_INTERVAL, int(self._opt(CONF_LIVE_INTERVAL, DEFAULT_LIVE_INTERVAL)))

    # Persistence ---------------------------------------------------------

    async def _async_load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        stored = await self._store.async_load() or {}
        if detector := stored.get("detector"):
            try:
                self.detector.state = DetectorState.from_dict(detector)
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("Discarding unreadable detector state")
        self._emitted = list(stored.get("emitted", []))

    @callback
    def _data_to_store(self) -> dict[str, Any]:
        state = self.detector.state
        return {
            "detector": state.as_dict() if state else None,
            "emitted": self._emitted[-MAX_EMITTED_KEYS:],
        }

    async def async_remove_store(self) -> None:
        """Delete persisted state when the entry is removed."""
        await self._store.async_remove()

    # Update --------------------------------------------------------------

    async def _async_update_data(self) -> TeamData:
        await self._async_load()
        previous = self.data or TeamData()
        now = dt_util.utcnow()

        games = previous.games
        if (
            not games
            or self._schedule_dirty
            or self._schedule_fetched is None
            or (now - self._schedule_fetched).total_seconds() > SCHEDULE_REFRESH_SECONDS
        ):
            try:
                games = await self.client.get_team_schedule(self.team_abbrev)
                self._schedule_fetched = now
                self._schedule_dirty = False
            except NhlApiError as err:
                if not games:
                    raise UpdateFailed(f"Team schedule unavailable: {err}") from err
                _LOGGER.warning("Keeping cached schedule for %s: %s", self.team_abbrev, err)

        events: list[NhlEvent] = []
        snapshot: GameSnapshot | None = None
        active = self._active_game(games, now)
        if active is not None:
            try:
                snapshot = await self.client.get_play_by_play(active.id)
            except NhlApiError as err:
                _LOGGER.warning("Play-by-play unavailable for %s: %s", active.id, err)
            if snapshot is not None:
                games = [snapshot.game if g.id == active.id else g for g in games]
                events.extend(self.detector.process(snapshot))
                if snapshot.game.state in FINISHED_STATES:
                    # Pull final records and the next game on the following poll
                    self._schedule_dirty = True

        data = self._build(games, snapshot, now, previous)
        events.extend(self._schedule_events(data, now))
        if events:
            self._dispatch(events, data)
        self._store.async_delay_save(self._data_to_store, 5)
        self.update_interval = timedelta(seconds=self._next_interval(data, now))
        return data

    def _active_game(self, games: list[Game], now: datetime) -> Game | None:
        """The game whose play-by-play should be polled now, if any."""
        lead = timedelta(minutes=PBP_LEAD_MINUTES)
        state = self.detector.state
        for game in games:
            if game.start_utc is None or game.schedule_state != "OK":
                continue
            if game.start_utc - lead > now or now - game.start_utc > timedelta(hours=MAX_GAME_HOURS):
                continue
            if game.state not in FINISHED_STATES:
                return game
            # Finished per schedule, but we have not seen the final yet
            if state is not None and state.game_id == game.id and "game_end" not in state.emitted:
                return game
        return None

    def _build(
        self,
        games: list[Game],
        snapshot: GameSnapshot | None,
        now: datetime,
        previous: TeamData,
    ) -> TeamData:
        today = dt_util.as_local(now).date()
        recent_cutoff = now - timedelta(hours=MAX_GAME_HOURS)
        upcoming = [
            g
            for g in games
            if g.start_utc
            and g.state not in FINISHED_STATES
            and g.start_utc >= recent_cutoff
            and g.schedule_state == "OK"
        ]
        finished = [g for g in games if g.state in FINISHED_STATES and g.start_utc]
        next_game = upcoming[0] if upcoming else None
        last_game = finished[-1] if finished else None
        todays = [g for g in games if g.start_utc and dt_util.as_local(g.start_utc).date() == today]
        if snapshot is not None:
            current = snapshot.game
        elif todays:
            current = todays[-1]
        else:
            current = next_game

        strength = pp_remaining = None
        if snapshot is not None and snapshot.game.state in LIVE_STATES:
            strength, pp_remaining = self._strength(snapshot)

        return TeamData(
            games=games,
            current_game=current,
            next_game=next_game,
            last_game=last_game,
            snapshot=snapshot,
            strength=strength,
            power_play_remaining=pp_remaining,
            last_events=previous.last_events,
        )

    def _strength(self, snapshot: GameSnapshot) -> tuple[str | None, str | None]:
        """Current strength (ev, pp, sh) and power play time left.

        The feed's situation block names the power play team as soon as a penalty is
        called. Without it, fall back to the last play's situationCode, which still shows
        the skater counts from before the penalty until the next faceoff.
        """
        game = snapshot.game
        sides = game.side_for(self.team_abbrev)
        if sides is None:
            return None, None
        if game.has_situation:
            if game.power_play_abbrev is None:
                return "ev", None
            strength = "pp" if game.power_play_abbrev == self.team_abbrev else "sh"
            return strength, game.power_play_remaining
        if not snapshot.plays:
            return None, None
        strength = strength_for(snapshot.plays[-1].situation_code, sides[2])
        return ("ev" if strength == "en" else strength), None

    def _schedule_events(self, data: TeamData, now: datetime) -> list[NhlEvent]:
        game = data.next_game
        if game is None or game.start_utc is None or game.state not in UPCOMING_STATES:
            return []
        events: list[NhlEvent] = []
        local_now = dt_util.as_local(now)
        sides = game.side_for(self.team_abbrev)
        if sides is None:
            return []
        team, opponent, is_home = sides
        payload = {
            "game_id": game.id,
            "team_abbrev": team.abbrev,
            "team_name": team.name,
            "opponent_abbrev": opponent.abbrev,
            "opponent_name": opponent.name,
            "is_home": is_home,
            "start_time": game.start_utc.isoformat(),
            "start_time_local": _clock_time(dt_util.as_local(game.start_utc)),
            "venue": game.venue,
        }
        game_day_hour = int(self._opt(CONF_GAME_DAY_HOUR, DEFAULT_GAME_DAY_HOUR))
        if (
            dt_util.as_local(game.start_utc).date() == local_now.date()
            and local_now.hour >= game_day_hour
            and now < game.start_utc
        ):
            key = f"{game.id}:game_day"
            if key not in self._emitted:
                events.append(NhlEvent(EVT_GAME_DAY, {"type": EVT_GAME_DAY, **payload}, key))
        soon = timedelta(minutes=int(self._opt(CONF_GAME_SOON_MINUTES, DEFAULT_GAME_SOON_MINUTES)))
        if game.start_utc - soon <= now < game.start_utc:
            key = f"{game.id}:game_soon"
            if key not in self._emitted:
                minutes = max(0, round((game.start_utc - now).total_seconds() / 60))
                events.append(
                    NhlEvent(
                        EVT_GAME_SOON,
                        {"type": EVT_GAME_SOON, **payload, "minutes_until_start": minutes},
                        key,
                    )
                )
        return events

    def _live_poll_delay(self, game_id: int) -> float:
        """Poll again just after the CDN copy expires, if that is sooner than the interval.

        The NHL rebuilds play-by-play every 20 s behind a 19 s CDN cache, so a
        poll timed to the cache expiry sees each new copy within about a second
        without polling more often.
        """
        interval = float(self.live_interval)
        stale = self.client.seconds_until_stale(f"gamecenter/{game_id}/play-by-play")
        if stale is not None and stale + CDN_REFRESH_SLACK < interval:
            return max(MIN_ALIGNED_POLL, stale + CDN_REFRESH_SLACK)
        return interval

    def _next_interval(self, data: TeamData, now: datetime) -> float:
        game = data.current_game
        if data.snapshot is not None and data.snapshot.game.state not in FINISHED_STATES:
            return self._live_poll_delay(data.snapshot.game.id)
        if self._schedule_dirty:
            return INTERVAL_PRE_GAME
        nxt = data.next_game
        if nxt is not None and nxt.start_utc is not None:
            until = (nxt.start_utc - now).total_seconds()
            soon = int(self._opt(CONF_GAME_SOON_MINUTES, DEFAULT_GAME_SOON_MINUTES))
            window = max(soon, PBP_LEAD_MINUTES) * 60 + INTERVAL_GAME_DAY
            if until <= window:
                return INTERVAL_PRE_GAME
            if dt_util.as_local(nxt.start_utc).date() == dt_util.as_local(now).date():
                return INTERVAL_GAME_DAY
        if game is not None and game.state in LIVE_STATES:
            return self.live_interval
        return INTERVAL_IDLE

    # Events --------------------------------------------------------------

    @callback
    def _dispatch(self, events: list[NhlEvent], data: TeamData) -> None:
        track_opponent = self._opt(CONF_TRACK_OPPONENT, DEFAULT_TRACK_OPPONENT)
        delay = int(self._opt(CONF_ALERT_DELAY, DEFAULT_ALERT_DELAY))
        for event in events:
            if event.key in self._emitted:
                continue
            self._emitted.append(event.key)
            if not track_opponent and (
                event.type in OPPONENT_EVENTS
                or (event.type == EVT_GOAL_UPDATED and event.data.get("side") == "opponent")
            ):
                continue
            if not self.alerts_enabled:
                _LOGGER.debug("Alerts off, suppressing %s", event.type)
                continue
            if delay > 0:
                async_call_later(
                    self.hass,
                    delay,
                    HassJob(partial(self._fire_delayed, event), cancel_on_shutdown=True),
                )
            else:
                self._fire(event, data)
        del self._emitted[:-MAX_EMITTED_KEYS]

    @callback
    def _fire_delayed(self, event: NhlEvent, _now: datetime) -> None:
        self._fire(event)

    @callback
    def _fire(self, event: NhlEvent, data: TeamData | None = None) -> None:
        if not self.alerts_enabled:
            _LOGGER.debug("Alerts turned off during delay, dropping %s", event.type)
            return
        payload = {**event.data, "config_entry_id": self.config_entry.entry_id}
        _LOGGER.debug("Firing %s for %s", event.type, self.team_abbrev)
        self.hass.bus.async_fire(EVENT_NHL, payload)
        target = data or self.data
        if target is not None:
            target.last_events[event.type] = payload
        async_dispatcher_send(
            self.hass, SIGNAL_EVENT.format(entry_id=self.config_entry.entry_id), event.type, payload
        )

    @callback
    def async_simulate(self, evt_type: str, overrides: dict[str, Any] | None = None) -> None:
        """Fire a sample event so users can test automations without a game."""
        data = self.data or TeamData()
        game = data.current_game or data.next_game
        team_name = self.config_entry.title
        opp_abbrev, opp_name, is_home, game_id = "OPP", "Opponent", True, 0
        if game is not None and (sides := game.side_for(self.team_abbrev)):
            team_name = sides[0].name
            opp_abbrev, opp_name, is_home = sides[1].abbrev, sides[1].name, sides[2]
            game_id = game.id
        scorer = {
            "id": 0,
            "name": "Test Player",
            "first_name": "Test",
            "last_name": "Player",
            "number": 99,
            "position": "C",
            "headshot": None,
            "season_total": 1,
        }
        payload: dict[str, Any] = {
            "type": evt_type,
            "simulated": True,
            "game_id": game_id,
            "team_abbrev": self.team_abbrev,
            "team_name": team_name,
            "opponent_abbrev": opp_abbrev,
            "opponent_name": opp_name,
            "is_home": is_home,
            "period": 2,
            "period_type": "REG",
            "period_label": period_label(2, "REG"),
            "time_in_period": "12:41",
            "time_remaining": "07:19",
            "score": {"team": 1, "opponent": 0},
            "event_id": None,
        }
        if "goal" in evt_type:
            payload.update(
                scorer=scorer,
                primary_assist={**scorer, "id": 1, "name": "Assist One", "number": 11},
                secondary_assist={**scorer, "id": 2, "name": "Assist Two", "number": 22},
                strength="ev",
                empty_net=False,
                shot_type="wrist",
            )
        if evt_type in (EVT_GAME_DAY, EVT_GAME_SOON):
            start = game.start_utc if game and game.start_utc else dt_util.utcnow() + timedelta(minutes=30)
            payload.update(
                start_time=start.isoformat(),
                start_time_local=_clock_time(dt_util.as_local(start)),
                venue=game.venue if game else None,
                minutes_until_start=max(0, round((start - dt_util.utcnow()).total_seconds() / 60)),
            )
        if "penalty" in evt_type:
            payload.update(
                committed_by=scorer,
                drawn_by=None,
                infraction="Hooking",
                penalty_type="MIN",
                duration_min=2,
            )
        payload.update(overrides or {})
        self._fire(NhlEvent(evt_type, payload, key=f"simulated:{dt_util.utcnow().timestamp()}"))
