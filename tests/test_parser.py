"""Parser tests against synthetic and (optionally) recorded payloads."""

from __future__ import annotations

import json
from pathlib import Path

from fake_nhl import FakeGame, club_schedule, league_schedule, standings
import pytest

from custom_components.nhl_companion.parser import (
    parse_club_schedule,
    parse_play_by_play,
    parse_schedule,
    parse_standings,
    text,
)

REAL = Path(__file__).parent / "fixtures" / "real"


def test_text_handles_localized_and_plain() -> None:
    assert text({"default": "Bruins", "fr": "Bruins"}) == "Bruins"
    assert text("Bruins") == "Bruins"
    assert text(None) is None


def test_play_by_play_live_goal() -> None:
    game = FakeGame()
    game.start_period(1)
    goal_id = game.goal("BOS", 8477956, 8479325, None, situation="1451")
    snap = parse_play_by_play(game.play_by_play())

    assert snap.game.state == "LIVE"
    assert snap.game.home.abbrev == "BOS"
    assert snap.game.home.name == "Boston Bruins"
    assert snap.game.home.score == 1
    assert snap.game.period == 1
    goal = next(p for p in snap.plays if p.event_id == goal_id)
    assert goal.type_key == "goal"
    assert goal.owner_team_id == 6
    assert snap.player(8477956).name == "David Pastrnak"
    assert snap.player(8477956).number == 88


def test_schedule_and_standings() -> None:
    game = FakeGame()
    days = parse_schedule(league_schedule([game], start=game.start))
    assert len(days) == 7
    assert days[0].games[0].id == game.id
    assert days[0].games[0].home.score is None

    games = parse_club_schedule(club_schedule("BOS", [game]))
    assert games[0].start_utc is not None

    rows = parse_standings(standings())
    assert rows[0].league_rank == 1
    assert rows[0].abbrev == "BOS"
    assert rows[0].last_10 == "6-3-1"


def test_missing_fields_do_not_crash() -> None:
    snap = parse_play_by_play({"id": 1, "plays": [{"eventId": 5}, {"nope": 1}], "rosterSpots": [{}]})
    assert snap.game.id == 1
    assert len(snap.plays) == 1
    assert snap.roster == {}


@pytest.mark.parametrize("path", sorted(REAL.glob("*.json")), ids=lambda p: p.name)
def test_recorded_fixtures_parse(path: Path) -> None:
    """Run scripts/record_fixtures.py to populate tests/fixtures/real/."""
    raw = json.loads(path.read_text())
    if "plays" in raw:
        snap = parse_play_by_play(raw)
        assert snap.game.id
    elif "standings" in raw:
        assert parse_standings(raw)
    elif "gameWeek" in raw:
        parse_schedule(raw)
    elif "games" in raw:
        parse_club_schedule(raw)
