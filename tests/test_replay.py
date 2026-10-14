"""Replay a real recorded game through the event detector.

Fixture: STL @ OTT, 2026-10-13 (game 2026020096), recorded live with
scripts/record_live.py from the 1st intermission to after the final, trimmed with
scripts/trim_recording.py. Recording started at 1-0 STL, so the first goal is the
baseline and is not announced.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from custom_components.nhl_companion.event_detector import EventDetector
from custom_components.nhl_companion.parser import parse_play_by_play

FIXTURE = Path(__file__).parent / "fixtures" / "replay" / "stl_ott_2026020096.json.gz"


def replay(team: str):
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    detector = EventDetector(team)
    events = []
    for raw in data["snapshots"]:
        events.extend(detector.process(parse_play_by_play({**raw, "rosterSpots": data["rosterSpots"]})))
    return events


def test_goals() -> None:
    goals = [
        (e.type, e.data["scorer"]["name"], e.data["period_label"], e.data["score"], e.data["strength"])
        for e in replay("STL")
        if e.type in ("team_goal", "opponent_goal")
    ]
    assert goals == [
        ("team_goal", "Jake Neighbours", "2nd", {"team": 2, "opponent": 0}, "ev"),
        # Posted as a missed-shot, turned into a goal one update later
        ("opponent_goal", "Claude Giroux", "2nd", {"team": 2, "opponent": 1}, "ev"),
        ("team_goal", "Mason McTavish", "2nd", {"team": 3, "opponent": 1}, "ev"),
        ("team_goal", "Pius Suter", "3rd", {"team": 4, "opponent": 1}, "ev"),
        ("team_goal", "Jake Neighbours", "3rd", {"team": 5, "opponent": 1}, "ev"),
        ("team_goal", "Mason McTavish", "3rd", {"team": 6, "opponent": 1}, "pp"),
        # Also posted as a missed-shot first
        ("team_goal", "Adam Jiricek", "3rd", {"team": 7, "opponent": 1}, "ev"),
        ("opponent_goal", "Fabian Zetterlund", "3rd", {"team": 7, "opponent": 2}, "pp"),
    ]


def test_assists_filled_in_later() -> None:
    events = replay("STL")
    final_assists = {}
    for e in events:
        if e.type in ("team_goal", "opponent_goal", "goal_updated"):
            final_assists[e.data["event_id"]] = (
                e.data["scorer"]["name"],
                [(e.data[k] or {}).get("name") for k in ("primary_assist", "secondary_assist")],
            )
    assert sorted(final_assists.values()) == sorted(
        [
            ("Jake Neighbours", ["Robert Thomas", "Dylan Holloway"]),
            ("Claude Giroux", ["Tim Stützle", "Drake Batherson"]),
            ("Mason McTavish", ["Jonatan Berggren", "Connor McMichael"]),
            ("Pius Suter", ["Ross Johnston", "Brandon Carlo"]),
            ("Jake Neighbours", ["Pavel Buchnevich", "Cam Fowler"]),
            ("Mason McTavish", ["Connor McMichael", "Pavel Buchnevich"]),
            ("Adam Jiricek", ["Pius Suter", "Mason McTavish"]),
            ("Fabian Zetterlund", ["Stephen Halliday", "Shane Pinto"]),
        ]
    )
    assert not [e for e in events if e.type == "goal_reversed"]


def test_penalties() -> None:
    penalties = [
        (e.type, e.data["committed_by"]["name"], e.data["infraction"], e.data["duration_min"])
        for e in replay("STL")
        if e.type in ("team_penalty", "opponent_penalty")
    ]
    # Posted as "minor" then corrected: Stanley to holding, Peterson and Donovan to
    # 5-minute fighting majors. Placeholder minors for Jiricek and McTavish were
    # deleted from the feed and must never be announced.
    assert penalties == [
        ("team_penalty", "Colton Parayko", "Tripping", 2),
        ("opponent_penalty", "Hoyt Stanley", "Holding", 2),
        ("team_penalty", "Dylan Peterson", "Fighting", 5),
        ("opponent_penalty", "Jorian Donovan", "Fighting", 5),
        ("opponent_penalty", "Warren Foegele", "Delaying game puck over glass", 2),
        ("team_penalty", "Philip Broberg", "Hooking", 2),
    ]


def test_periods_and_result() -> None:
    flow = [
        (e.type, e.data["period_label"])
        for e in replay("STL")
        if e.type.startswith(("period", "intermission", "game"))
    ]
    assert flow == [
        ("intermission_end", "2nd"),
        ("period_start", "2nd"),
        ("period_end", "2nd"),
        ("intermission_start", "2nd"),
        ("intermission_end", "3rd"),
        ("period_start", "3rd"),
        ("period_end", "3rd"),
        # Fired on gameState OVER, one update before FINAL
        ("game_end_win", "3rd"),
    ]


def test_goal_videos_once_per_clip() -> None:
    clips = [(e.data["event_id"], e.data["clip_type"]) for e in replay("STL") if e.type == "goal_highlight"]
    assert len(clips) == len(set(clips))
    assert {c for _, c in clips} == {"short", "full"}


def test_opponent_view_mirrors() -> None:
    events = replay("OTT")
    assert [e.data["scorer"]["name"] for e in events if e.type == "team_goal"] == [
        "Claude Giroux",
        "Fabian Zetterlund",
    ]
    assert [e.type for e in events if e.type.startswith("game_end")] == ["game_end_loss"]
