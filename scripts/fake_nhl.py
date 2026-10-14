"""Synthetic NHL API payloads shaped like api-web.nhle.com/v1 responses.

Used by the test suite and by mock_nhl_server.py. Field names follow the
community docs (gitlab.com/dword4/nhlapi new-api.md, github.com/Zmalski/NHL-API-Reference).
Replace with real captures via scripts/record_fixtures.py when possible.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

TEAM_INFO: dict[str, dict[str, Any]] = {
    "BOS": {"id": 6, "place": "Boston", "common": "Bruins", "conf": "Eastern", "div": "Atlantic"},
    "TOR": {"id": 10, "place": "Toronto", "common": "Maple Leafs", "conf": "Eastern", "div": "Atlantic"},
    "MTL": {"id": 8, "place": "Montréal", "common": "Canadiens", "conf": "Eastern", "div": "Atlantic"},
    "NYR": {"id": 3, "place": "New York", "common": "Rangers", "conf": "Eastern", "div": "Metropolitan"},
    "EDM": {"id": 22, "place": "Edmonton", "common": "Oilers", "conf": "Western", "div": "Pacific"},
    "COL": {"id": 21, "place": "Colorado", "common": "Avalanche", "conf": "Western", "div": "Central"},
}

ROSTERS: dict[str, list[tuple[int, str, str, int, str]]] = {
    "BOS": [
        (8477956, "David", "Pastrnak", 88, "R"),
        (8479325, "Charlie", "McAvoy", 73, "D"),
        (8482072, "Morgan", "Geekie", 39, "C"),
        (8480280, "Jeremy", "Swayman", 1, "G"),
    ],
    "TOR": [
        (8479318, "Auston", "Matthews", 34, "C"),
        (8477939, "William", "Nylander", 88, "R"),
        (8476853, "Morgan", "Rielly", 44, "D"),
        (8479361, "Joseph", "Woll", 60, "G"),
    ],
}


def _team_block(abbrev: str, score: int | None = None, sog: int | None = None) -> dict[str, Any]:
    info = TEAM_INFO.get(abbrev, {"id": 99, "place": abbrev, "common": abbrev})
    block: dict[str, Any] = {
        "id": info["id"],
        "commonName": {"default": info["common"]},
        "placeName": {"default": info["place"]},
        "abbrev": abbrev,
        "logo": f"https://assets.nhle.com/logos/nhl/svg/{abbrev}_light.svg",
        "darkLogo": f"https://assets.nhle.com/logos/nhl/svg/{abbrev}_dark.svg",
    }
    if score is not None:
        block["score"] = score
    if sog is not None:
        block["sog"] = sog
    return block


def _roster(abbrev: str) -> list[tuple[int, str, str, int, str]]:
    if abbrev in ROSTERS:
        return ROSTERS[abbrev]
    base = TEAM_INFO.get(abbrev, {"id": 99})["id"] * 1000
    return [(base + i, "Player", f"{abbrev}{i}", i, "C") for i in range(1, 5)]


class FakeGame:
    """Mutable game that renders play-by-play and schedule JSON."""

    def __init__(
        self,
        home: str = "BOS",
        away: str = "TOR",
        start: datetime | None = None,
        game_id: int = 2025020100,
    ) -> None:
        self.id = game_id
        self.home = home
        self.away = away
        self.start = start or datetime.now(UTC) + timedelta(hours=2)
        self.state = "FUT"
        self.period = 0
        self.period_type = "REG"
        self.in_intermission = False
        self.time_remaining = "20:00"
        self.score = {home: 0, away: 0}
        self.sog = {home: 0, away: 0}
        self.last_period_type: str | None = None
        self.plays: list[dict[str, Any]] = []
        self._next_event = 100
        self._sort = 0

    # helpers --------------------------------------------------------------

    def team_id(self, abbrev: str) -> int:
        return TEAM_INFO.get(abbrev, {"id": 99})["id"]

    def _add_play(
        self,
        type_key: str,
        details: dict[str, Any] | None = None,
        situation: str = "1551",
        time_in_period: str = "05:00",
    ) -> int:
        self._next_event += 1
        self._sort += 10
        mins, secs = (int(x) for x in time_in_period.split(":"))
        remaining = max(0, 20 * 60 - (mins * 60 + secs))
        play = {
            "eventId": self._next_event,
            "periodDescriptor": {
                "number": self.period,
                "periodType": self.period_type,
                "maxRegulationPeriods": 3,
            },
            "timeInPeriod": time_in_period,
            "timeRemaining": f"{remaining // 60:02d}:{remaining % 60:02d}",
            "situationCode": situation,
            "homeTeamDefendingSide": "left",
            "typeCode": 0,
            "typeDescKey": type_key,
            "sortOrder": self._sort,
        }
        if details is not None:
            play["details"] = details
        self.plays.append(play)
        self.time_remaining = play["timeRemaining"]
        return self._next_event

    # game actions -----------------------------------------------------------

    def pregame(self) -> None:
        self.state = "PRE"

    def start_period(self, number: int, period_type: str = "REG") -> int:
        self.state = "LIVE"
        self.period = number
        self.period_type = period_type
        self.in_intermission = False
        return self._add_play("period-start", time_in_period="00:00")

    def end_period(self, intermission: bool = True) -> int:
        event_id = self._add_play("period-end", time_in_period="20:00")
        self.in_intermission = intermission
        return event_id

    def goal(
        self,
        abbrev: str,
        scorer: int,
        assist1: int | None = None,
        assist2: int | None = None,
        situation: str = "1551",
        time_in_period: str = "05:00",
    ) -> int:
        self.score[abbrev] += 1
        self.sog[abbrev] += 1
        details: dict[str, Any] = {
            "xCoord": 70,
            "yCoord": -5,
            "zoneCode": "O",
            "shotType": "wrist",
            "scoringPlayerId": scorer,
            "scoringPlayerTotal": 10,
            "eventOwnerTeamId": self.team_id(abbrev),
            "goalieInNetId": 8479361,
            "awaySOG": self.sog[self.away],
            "homeSOG": self.sog[self.home],
            "awayScore": self.score[self.away],
            "homeScore": self.score[self.home],
            "highlightClipSharingUrl": "https://nhl.com/video/example",
        }
        if assist1:
            details.update(assist1PlayerId=assist1, assist1PlayerTotal=20)
        if assist2:
            details.update(assist2PlayerId=assist2, assist2PlayerTotal=5)
        return self._add_play("goal", details, situation, time_in_period)

    def penalty(
        self,
        abbrev: str,
        committed: int,
        drawn: int | None = None,
        desc: str = "hooking",
        minutes: int = 2,
        time_in_period: str = "08:00",
    ) -> int:
        details: dict[str, Any] = {
            "typeCode": "MIN",
            "descKey": desc,
            "duration": minutes,
            "committedByPlayerId": committed,
            "eventOwnerTeamId": self.team_id(abbrev),
        }
        if drawn:
            details["drawnByPlayerId"] = drawn
        return self._add_play("penalty", details, "1551", time_in_period)

    def shot(self, abbrev: str, shooter: int) -> int:
        self.sog[abbrev] += 1
        return self._add_play(
            "shot-on-goal", {"shootingPlayerId": shooter, "eventOwnerTeamId": self.team_id(abbrev)}
        )

    def remove_play(self, event_id: int, abbrev: str | None = None) -> None:
        """Simulate an overturned goal: the play disappears and the score drops."""
        self.plays = [p for p in self.plays if p["eventId"] != event_id]
        if abbrev:
            self.score[abbrev] -= 1

    def missed_shot(self, abbrev: str, shooter: int, time_in_period: str = "05:00") -> int:
        return self._add_play(
            "missed-shot",
            {"shootingPlayerId": shooter, "eventOwnerTeamId": self.team_id(abbrev)},
            time_in_period=time_in_period,
        )

    def convert_to_goal(self, event_id: int, abbrev: str, scorer: int) -> None:
        """Turn an existing play into a goal in place, as the live feed did for a missed shot."""
        self.score[abbrev] += 1
        for play in self.plays:
            if play["eventId"] == event_id:
                play.update(typeCode=505, typeDescKey="goal")
                details = play.setdefault("details", {})
                details.pop("shootingPlayerId", None)
                details.update(
                    scoringPlayerId=scorer,
                    scoringPlayerTotal=1,
                    eventOwnerTeamId=self.team_id(abbrev),
                    awayScore=self.score[self.away],
                    homeScore=self.score[self.home],
                )

    def amend(self, event_id: int, **details: Any) -> None:
        """Edit a play's details after it appeared, as the NHL does with assists."""
        for play in self.plays:
            if play["eventId"] == event_id:
                play.setdefault("details", {}).update(details)

    def end_intermission(self) -> None:
        self.in_intermission = False

    def final(self, last_period_type: str = "REG") -> None:
        self._add_play("game-end", time_in_period="20:00")
        self.state = "OFF"
        self.last_period_type = last_period_type
        self.in_intermission = False

    # renderers --------------------------------------------------------------

    def _started(self) -> bool:
        return self.state not in ("FUT", "PRE")

    def schedule_game(self) -> dict[str, Any]:
        started = self._started()
        game: dict[str, Any] = {
            "id": self.id,
            "season": 20252026,
            "gameType": 2,
            "venue": {"default": "TD Garden"},
            "neutralSite": False,
            "startTimeUTC": self.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "easternUTCOffset": "-04:00",
            "venueUTCOffset": "-04:00",
            "venueTimezone": "America/New_York",
            "gameState": self.state,
            "gameScheduleState": "OK",
            "tvBroadcasts": [],
            "awayTeam": _team_block(self.away, self.score[self.away] if started else None),
            "homeTeam": _team_block(self.home, self.score[self.home] if started else None),
            "periodDescriptor": {"number": max(self.period, 1), "periodType": self.period_type},
            "gameCenterLink": f"/gamecenter/{self.away.lower()}-vs-{self.home.lower()}/{self.id}",
        }
        if self.last_period_type:
            game["gameOutcome"] = {"lastPeriodType": self.last_period_type}
        return game

    def play_by_play(self) -> dict[str, Any]:
        started = self._started()
        roster = []
        for abbrev in (self.home, self.away):
            for pid, first, last, num, pos in _roster(abbrev):
                roster.append(
                    {
                        "teamId": self.team_id(abbrev),
                        "playerId": pid,
                        "firstName": {"default": first},
                        "lastName": {"default": last},
                        "sweaterNumber": num,
                        "positionCode": pos,
                        "headshot": f"https://assets.nhle.com/mugs/nhl/20252026/{abbrev}/{pid}.png",
                    }
                )
        data: dict[str, Any] = {
            "id": self.id,
            "season": 20252026,
            "gameType": 2,
            "limitedScoring": False,
            "gameDate": self.start.strftime("%Y-%m-%d"),
            "venue": {"default": "TD Garden"},
            "venueLocation": {"default": "Boston"},
            "startTimeUTC": self.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "easternUTCOffset": "-04:00",
            "venueUTCOffset": "-04:00",
            "tvBroadcasts": [],
            "gameState": self.state,
            "gameScheduleState": "OK",
            "periodDescriptor": {
                "number": max(self.period, 1),
                "periodType": self.period_type,
                "maxRegulationPeriods": 3,
            },
            "awayTeam": _team_block(
                self.away,
                self.score[self.away] if started else None,
                self.sog[self.away] if started else None,
            ),
            "homeTeam": _team_block(
                self.home,
                self.score[self.home] if started else None,
                self.sog[self.home] if started else None,
            ),
            "shootoutInUse": True,
            "otInUse": True,
            "clock": {
                "timeRemaining": self.time_remaining,
                "secondsRemaining": 0,
                "running": self.state == "LIVE" and not self.in_intermission,
                "inIntermission": self.in_intermission,
            },
            "displayPeriod": max(self.period, 1),
            "rosterSpots": roster,
            "regPeriods": 3,
            "plays": deepcopy(self.plays),
        }
        if self.last_period_type:
            data["gameOutcome"] = {"lastPeriodType": self.last_period_type}
        return data


def club_schedule(team: str, games: list[FakeGame]) -> dict[str, Any]:
    return {
        "previousSeason": 20242025,
        "currentSeason": 20252026,
        "clubTimezone": "America/New_York",
        "clubUTCOffset": "-04:00",
        "games": [g.schedule_game() for g in games if team in (g.home, g.away)],
    }


def league_schedule(games: list[FakeGame], start: datetime | None = None) -> dict[str, Any]:
    start = start or datetime.now(UTC)
    days = []
    for offset in range(7):
        day = (start + timedelta(days=offset)).date()
        todays = [g.schedule_game() for g in games if g.start.date() == day]
        days.append(
            {
                "date": day.isoformat(),
                "dayAbbrev": day.strftime("%a").upper(),
                "numberOfGames": len(todays),
                "games": todays,
            }
        )
    return {
        "nextStartDate": (start + timedelta(days=7)).date().isoformat(),
        "previousStartDate": (start - timedelta(days=7)).date().isoformat(),
        "gameWeek": days,
    }


def standings() -> dict[str, Any]:
    rows = []
    for rank, (abbrev, info) in enumerate(TEAM_INFO.items(), start=1):
        wins, losses, otl = 20 - rank, 5 + rank, 3
        rows.append(
            {
                "conferenceName": info["conf"],
                "divisionName": info["div"],
                "teamName": {"default": f"{info['place']} {info['common']}"},
                "teamCommonName": {"default": info["common"]},
                "teamAbbrev": {"default": abbrev},
                "teamLogo": f"https://assets.nhle.com/logos/nhl/svg/{abbrev}_light.svg",
                "gamesPlayed": wins + losses + otl,
                "wins": wins,
                "losses": losses,
                "otLosses": otl,
                "points": wins * 2 + otl,
                "pointPctg": round((wins * 2 + otl) / ((wins + losses + otl) * 2), 3),
                "goalDifferential": 30 - rank * 8,
                "leagueSequence": rank,
                "conferenceSequence": rank,
                "divisionSequence": rank,
                "wildcardSequence": 0,
                "streakCode": "W" if rank % 2 else "L",
                "streakCount": rank,
                "l10Wins": 6,
                "l10Losses": 3,
                "l10OtLosses": 1,
            }
        )
    return {"wildCardIndicator": True, "standingsDateTimeUtc": "2025-11-01T12:00:00Z", "standings": rows}
