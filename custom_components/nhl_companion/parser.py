"""Convert raw NHL API JSON into models.

The NHL web API is undocumented and changes without notice. Every field is
read defensively so a schema change degrades a value instead of breaking the
integration. Keep all knowledge of the raw JSON shape in this module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .const import LOGO_URL_TEMPLATE, TEAMS
from .models import Clip, Game, GameSnapshot, Play, Player, ScheduleDay, Standing, TeamSide


def text(value: Any) -> str | None:
    """Read a localized field ({"default": "x"}) or a plain string."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("default") or next(iter(value.values()), None)
    return str(value)


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO 8601 UTC timestamp like 2025-10-08T23:00:00Z."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_team_side(raw: dict[str, Any] | None) -> TeamSide:
    """Parse a homeTeam/awayTeam block from any endpoint."""
    raw = raw or {}
    abbrev = text(raw.get("abbrev")) or ""
    place = text(raw.get("placeName"))
    common = text(raw.get("commonName"))
    full = text(raw.get("name"))
    name = f"{place} {common}" if place and common else full or common or place or TEAMS.get(abbrev, abbrev)
    logo = raw.get("logo") or (LOGO_URL_TEMPLATE.format(abbrev=abbrev) if abbrev else None)
    return TeamSide(
        id=_int(raw.get("id")),
        abbrev=abbrev,
        name=name,
        logo=logo,
        score=_int(raw.get("score")),
        sog=_int(raw.get("sog")),
    )


def parse_situation(raw: Any) -> tuple[bool, str | None, str | None]:
    """Parse the play-by-play "situation" block: (present, power play team, PP time left).

    Example: {"homeTeam": {"abbrev": "OTT", "situationDescriptions": ["PP"], "strength": 5},
    "awayTeam": {"abbrev": "STL", "strength": 4}, "situationCode": "1451", "timeRemaining": "02:00"}.
    A delayed penalty shows "EN" (extra attacker), not "PP".
    """
    if not isinstance(raw, dict):
        return False, None, None
    for key in ("homeTeam", "awayTeam"):
        side = raw.get(key) or {}
        if "PP" in (side.get("situationDescriptions") or []):
            return True, text(side.get("abbrev")), raw.get("timeRemaining")
    return True, None, None


def parse_game(raw: dict[str, Any]) -> Game:
    """Parse a game object (schedule, club schedule, score or play-by-play root)."""
    period = raw.get("periodDescriptor") or {}
    clock = raw.get("clock") or {}
    outcome = raw.get("gameOutcome") or {}
    has_situation, pp_abbrev, pp_remaining = parse_situation(raw.get("situation"))
    return Game(
        id=_int(raw.get("id")) or 0,
        season=_int(raw.get("season")),
        game_type=_int(raw.get("gameType")),
        start_utc=parse_datetime(raw.get("startTimeUTC")),
        state=str(raw.get("gameState") or "FUT"),
        schedule_state=str(raw.get("gameScheduleState") or "OK"),
        venue=text(raw.get("venue")),
        home=parse_team_side(raw.get("homeTeam")),
        away=parse_team_side(raw.get("awayTeam")),
        period=_int(period.get("number")),
        period_type=period.get("periodType"),
        clock=clock.get("timeRemaining"),
        in_intermission=bool(clock.get("inIntermission", False)),
        last_period_type=outcome.get("lastPeriodType"),
        has_situation=has_situation,
        power_play_abbrev=pp_abbrev,
        power_play_remaining=pp_remaining,
    )


def parse_schedule(raw: dict[str, Any]) -> list[ScheduleDay]:
    """Parse /schedule/{date} or /schedule/now."""
    days: list[ScheduleDay] = []
    for day in raw.get("gameWeek") or []:
        games = [parse_game(g) for g in day.get("games") or []]
        days.append(ScheduleDay(date=str(day.get("date", "")), games=games))
    return days


def parse_club_schedule(raw: dict[str, Any]) -> list[Game]:
    """Parse /club-schedule-season/{team}/now."""
    games = [parse_game(g) for g in raw.get("games") or []]
    games.sort(key=lambda g: (g.start_utc is None, g.start_utc))
    return games


def parse_player(raw: dict[str, Any]) -> Player | None:
    """Parse a rosterSpots entry."""
    player_id = _int(raw.get("playerId"))
    if player_id is None:
        return None
    first = text(raw.get("firstName")) or ""
    last = text(raw.get("lastName")) or ""
    return Player(
        id=player_id,
        name=f"{first} {last}".strip(),
        first_name=first,
        last_name=last,
        number=_int(raw.get("sweaterNumber")),
        position=raw.get("positionCode"),
        team_id=_int(raw.get("teamId")),
        headshot=raw.get("headshot"),
    )


def parse_play(raw: dict[str, Any]) -> Play | None:
    """Parse one entry of the plays array."""
    event_id = _int(raw.get("eventId"))
    if event_id is None:
        return None
    period = raw.get("periodDescriptor") or {}
    return Play(
        event_id=event_id,
        sort_order=_int(raw.get("sortOrder")) or 0,
        type_key=str(raw.get("typeDescKey") or ""),
        period=_int(period.get("number")),
        period_type=period.get("periodType"),
        time_in_period=raw.get("timeInPeriod"),
        time_remaining=raw.get("timeRemaining"),
        situation_code=raw.get("situationCode"),
        details=raw.get("details") or {},
    )


def parse_play_by_play(raw: dict[str, Any]) -> GameSnapshot:
    """Parse /gamecenter/{id}/play-by-play."""
    game = parse_game(raw)
    roster: dict[int, Player] = {}
    for spot in raw.get("rosterSpots") or []:
        if (player := parse_player(spot)) is not None:
            roster[player.id] = player
    plays = [p for p in (parse_play(r) for r in raw.get("plays") or []) if p]
    plays.sort(key=lambda p: (p.sort_order, p.event_id))
    return GameSnapshot(game=game, plays=plays, roster=roster)


def parse_standings(raw: dict[str, Any]) -> list[Standing]:
    """Parse /standings/now."""
    rows: list[Standing] = []
    for row in raw.get("standings") or []:
        abbrev = text(row.get("teamAbbrev")) or ""
        l10 = None
        if row.get("l10Wins") is not None:
            l10 = f"{row.get('l10Wins', 0)}-{row.get('l10Losses', 0)}-{row.get('l10OtLosses', 0)}"
        streak = None
        if row.get("streakCode"):
            streak = f"{row['streakCode']}{row.get('streakCount', '')}"
        rows.append(
            Standing(
                abbrev=abbrev,
                name=text(row.get("teamName")) or TEAMS.get(abbrev, abbrev),
                logo=row.get("teamLogo") or (LOGO_URL_TEMPLATE.format(abbrev=abbrev) if abbrev else None),
                conference=row.get("conferenceName"),
                division=row.get("divisionName"),
                games_played=_int(row.get("gamesPlayed")) or 0,
                wins=_int(row.get("wins")) or 0,
                losses=_int(row.get("losses")) or 0,
                ot_losses=_int(row.get("otLosses")) or 0,
                points=_int(row.get("points")) or 0,
                point_pct=_float(row.get("pointPctg")),
                goal_differential=_int(row.get("goalDifferential")),
                league_rank=_int(row.get("leagueSequence")),
                conference_rank=_int(row.get("conferenceSequence")),
                division_rank=_int(row.get("divisionSequence")),
                wildcard_rank=_int(row.get("wildcardSequence")),
                streak=streak,
                last_10=l10,
            )
        )
    rows.sort(key=lambda s: (s.league_rank is None, s.league_rank or 0))
    return rows


def parse_three_stars(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse summary.threeStars from /gamecenter/{id}/landing (empty until after the final)."""
    stars = []
    for row in (raw.get("summary") or {}).get("threeStars") or []:
        if not isinstance(row, dict):
            continue
        stars.append(
            {
                "star": _int(row.get("star")),
                "id": _int(row.get("playerId")),
                "name": text(row.get("name")),
                "team_abbrev": text(row.get("teamAbbrev")),
                "number": _int(row.get("sweaterNo")),
                "position": row.get("position"),
                "headshot": row.get("headshot"),
                "goals": _int(row.get("goals")),
                "assists": _int(row.get("assists")),
                "points": _int(row.get("points")),
                "save_pct": _float(row.get("savePctg")),
                "goals_against_avg": _float(row.get("goalsAgainstAverage")),
            }
        )
    stars.sort(key=lambda s: s["star"] or 9)
    return stars


def parse_clip(raw: dict[str, Any]) -> Clip:
    """Parse a Brightcove Playback API video: prefer the largest HTTPS MP4 and HTTPS HLS."""
    mp4s = [
        s
        for s in raw.get("sources") or []
        if s.get("container") == "MP4" and str(s.get("src", "")).startswith("https://")
    ]
    mp4s.sort(key=lambda s: _int(s.get("height")) or 0, reverse=True)
    hls = next(
        (
            s["src"]
            for s in raw.get("sources") or []
            if s.get("type") == "application/x-mpegURL" and str(s.get("src", "")).startswith("https://")
        ),
        None,
    )
    duration = _float(raw.get("duration"))
    return Clip(
        id=str(raw.get("id") or ""),
        title=raw.get("name"),
        duration_s=round(duration / 1000, 1) if duration else None,
        mp4=mp4s[0]["src"] if mp4s else None,
        hls=hls,
        poster=raw.get("poster"),
    )
