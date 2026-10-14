"""Parser tests against synthetic and (optionally) recorded payloads."""

from __future__ import annotations

import json
from pathlib import Path

from fake_nhl import FakeGame, club_schedule, league_schedule, standings
import pytest

from custom_components.nhl_companion.parser import (
    parse_clip,
    parse_club_schedule,
    parse_play_by_play,
    parse_schedule,
    parse_standings,
    parse_three_stars,
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


def test_situation_block() -> None:
    game = FakeGame()
    game.start_period(1)
    assert parse_play_by_play(game.play_by_play()).game.has_situation is False

    game.power_play("TOR", "01:35")
    snap = parse_play_by_play(game.play_by_play())
    assert snap.game.has_situation is True
    assert snap.game.power_play_abbrev == "TOR"
    assert snap.game.power_play_remaining == "01:35"

    game.delayed_penalty("TOR")
    snap = parse_play_by_play(game.play_by_play())
    assert snap.game.has_situation is True
    assert snap.game.power_play_abbrev is None


def test_parse_clip() -> None:
    """Shape of a Brightcove Playback API response for an NHL goal clip (trimmed)."""
    clip = parse_clip(
        {
            "id": "6406808612112",
            "name": "STL@OTT: McTavish scores goal against Samuel Ersson",
            "duration": 45743,
            "poster": "https://cf-images.us-east-1.prod.boltdns.net/poster.jpg",
            "sources": [
                {"type": "application/x-mpegURL", "src": "http://manifest.prod.boltdns.net/hls"},
                {"type": "application/x-mpegURL", "src": "https://manifest.prod.boltdns.net/hls"},
                {"type": "application/dash+xml", "src": "https://manifest.prod.boltdns.net/dash"},
                {"container": "MP4", "codec": "H264", "height": 360, "src": "https://cdn/360.mp4"},
                {"container": "MP4", "codec": "H264", "height": 720, "src": "http://cdn/720.mp4"},
                {"container": "MP4", "codec": "H264", "height": 720, "src": "https://cdn/720.mp4"},
            ],
        }
    )
    assert clip.id == "6406808612112"
    assert clip.duration_s == 45.7
    assert clip.mp4 == "https://cdn/720.mp4"
    assert clip.hls == "https://manifest.prod.boltdns.net/hls"
    assert parse_clip({"sources": []}).mp4 is None


def test_parse_three_stars() -> None:
    assert parse_three_stars({"summary": {"threeStars": []}}) == []
    stars = parse_three_stars(
        {
            "summary": {
                "threeStars": [
                    {"star": 2, "playerId": 2, "teamAbbrev": "OTT", "name": {"default": "B. Two"}},
                    {
                        "star": 1,
                        "playerId": 1,
                        "teamAbbrev": "STL",
                        "name": {"default": "A. One"},
                        "sweaterNo": 9,
                        "position": "C",
                        "goals": 2,
                        "assists": 1,
                        "points": 3,
                    },
                ]
            }
        }
    )
    assert [s["name"] for s in stars] == ["A. One", "B. Two"]
    assert stars[0]["points"] == 3
    assert stars[0]["number"] == 9


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
