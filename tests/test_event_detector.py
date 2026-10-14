"""Event detection from replayed snapshot sequences."""

from __future__ import annotations

from fake_nhl import FakeGame

from custom_components.nhl_companion.event_detector import (
    MAX_PENALTY_HOLD_POLLS,
    DetectorState,
    EventDetector,
    period_label,
    strength_for,
)
from custom_components.nhl_companion.parser import parse_play_by_play

BOS_PASTA, BOS_MCAVOY, BOS_GEEKIE = 8477956, 8479325, 8482072
TOR_MATTHEWS, TOR_NYLANDER = 8479318, 8477939


def types(events) -> list[str]:
    return [e.type for e in events]


def step(detector: EventDetector, game: FakeGame):
    return detector.process(parse_play_by_play(game.play_by_play()))


def test_full_game_sequence() -> None:
    game = FakeGame()
    det = EventDetector("BOS")
    assert step(det, game) == []  # baseline

    game.pregame()
    assert step(det, game) == []

    game.start_period(1)
    assert types(step(det, game)) == ["game_start", "period_start"]

    game.goal("BOS", BOS_PASTA, BOS_MCAVOY, BOS_GEEKIE, time_in_period="04:12")
    (goal,) = step(det, game)
    assert goal.type == "team_goal"
    assert goal.data["scorer"]["name"] == "David Pastrnak"
    assert goal.data["primary_assist"]["name"] == "Charlie McAvoy"
    assert goal.data["secondary_assist"]["name"] == "Morgan Geekie"
    assert goal.data["score"] == {"team": 1, "opponent": 0}
    assert goal.data["time_in_period"] == "04:12"
    assert goal.data["time_remaining"] == "15:48"
    assert goal.data["period_label"] == "1st"
    assert goal.data["strength"] == "ev"
    assert goal.data["opponent_abbrev"] == "TOR"

    game.penalty("TOR", TOR_NYLANDER, BOS_PASTA, desc="tripping")
    (pen,) = step(det, game)
    assert pen.type == "opponent_penalty"
    assert pen.data["committed_by"]["name"] == "William Nylander"
    assert pen.data["infraction"] == "Tripping"
    assert pen.data["duration_min"] == 2

    game.goal("TOR", TOR_MATTHEWS, situation="1551")
    (opp,) = step(det, game)
    assert opp.type == "opponent_goal"
    assert opp.data["score"] == {"team": 1, "opponent": 1}

    game.end_period(intermission=True)
    assert types(step(det, game)) == ["period_end", "intermission_start"]

    game.start_period(2)
    assert types(step(det, game)) == ["period_start", "intermission_end"]

    # No change, no events
    assert step(det, game) == []

    game.goal("BOS", BOS_GEEKIE)
    game.final()
    assert types(step(det, game)) == ["team_goal", "game_end_win"]
    assert step(det, game) == []


def test_assists_added_later_fire_goal_updated() -> None:
    """Live STL@OTT 2026-10-13: assists arrived 20 s and 40 s after the goal."""
    game = FakeGame()
    game.start_period(1)
    det = EventDetector("BOS")
    step(det, game)

    goal_id = game.goal("BOS", BOS_PASTA)
    (goal,) = step(det, game)
    assert goal.type == "team_goal"
    assert goal.data["primary_assist"] is None

    game.amend(goal_id, assist1PlayerId=BOS_MCAVOY, assist1PlayerTotal=4)
    (upd,) = step(det, game)
    assert upd.type == "goal_updated"
    assert upd.data["side"] == "team"
    assert upd.data["changed"] == ["primary_assist"]
    assert upd.data["primary_assist"]["name"] == "Charlie McAvoy"
    assert upd.data["scorer"]["name"] == "David Pastrnak"
    assert upd.data["score"] == {"team": 1, "opponent": 0}

    # Clip and time edits are not player changes
    game.amend(goal_id, highlightClipSharingUrl="https://nhl.com/video/x")
    assert step(det, game) == []

    game.amend(goal_id, assist2PlayerId=BOS_GEEKIE, scoringPlayerId=BOS_MCAVOY, assist1PlayerId=BOS_PASTA)
    (upd,) = step(det, game)
    assert upd.data["changed"] == ["scorer", "primary_assist", "secondary_assist"]
    assert upd.data["scorer"]["name"] == "Charlie McAvoy"
    assert upd.key != goal.key


def test_play_that_turns_into_a_goal_fires_goal() -> None:
    """Live STL@OTT 2026-10-13: eventId 755 went from missed-shot to goal in place."""
    game = FakeGame()
    game.start_period(1)
    det = EventDetector("BOS")
    step(det, game)

    shot_id = game.missed_shot("TOR", TOR_MATTHEWS)
    assert step(det, game) == []

    game.convert_to_goal(shot_id, "TOR", TOR_MATTHEWS)
    (goal,) = step(det, game)
    assert goal.type == "opponent_goal"
    assert goal.data["event_id"] == shot_id
    assert goal.data["scorer"]["name"] == "Auston Matthews"
    assert goal.data["score"] == {"team": 0, "opponent": 1}
    assert step(det, game) == []


def test_goal_that_stops_being_a_goal_is_reversed() -> None:
    game = FakeGame()
    game.start_period(1)
    det = EventDetector("BOS")
    step(det, game)
    goal_id = game.goal("BOS", BOS_PASTA)
    assert types(step(det, game)) == ["team_goal"]

    for play in game.plays:
        if play["eventId"] == goal_id:
            play.update(typeDescKey="missed-shot", typeCode=507)
    game.score["BOS"] -= 1
    (rev,) = step(det, game)
    assert rev.type == "goal_reversed"
    assert rev.data["event_id"] == goal_id
    assert rev.data["side"] == "team"


def test_goal_videos_fire_goal_highlight_once_per_clip() -> None:
    """Live STL@OTT 2026-10-13: a short clip ~5 min and a full highlight ~9 min after the goal."""
    game = FakeGame()
    game.start_period(1)
    det = EventDetector("BOS")
    step(det, game)
    goal_id = game.goal("BOS", BOS_PASTA, BOS_MCAVOY)
    assert types(step(det, game)) == ["team_goal"]

    game.amend(goal_id, discreteClip=6406807775112)
    (short,) = step(det, game)
    assert short.type == "goal_highlight"
    assert short.data["clip_type"] == "short"
    assert short.data["clip_id"] == "6406807775112"
    assert short.data["side"] == "team"
    assert short.data["scorer"]["name"] == "David Pastrnak"
    assert step(det, game) == []

    game.amend(
        goal_id,
        highlightClip=6406806930112,
        highlightClipSharingUrl="https://nhl.com/video/x-6406806930112",
    )
    (full,) = step(det, game)
    assert full.data["clip_type"] == "full"
    assert full.data["clip_id"] == "6406806930112"
    assert full.data["highlight_url"] == "https://nhl.com/video/x-6406806930112"
    assert step(det, game) == []


def test_goal_highlight_not_replayed_after_restart() -> None:
    game = FakeGame()
    game.start_period(1)
    goal_id = game.goal("BOS", BOS_PASTA)
    game.amend(goal_id, discreteClip=1)
    det = EventDetector("BOS")
    step(det, game)  # baseline sees the clip already posted
    assert step(det, game) == []

    # State saved before clips were tracked
    saved = det.state.as_dict()
    for goal in saved["goals"].values():
        goal.pop("clips")
    restored = EventDetector("BOS", DetectorState.from_dict(saved))
    assert step(restored, game) == []
    game.amend(goal_id, highlightClip=2)
    assert types(step(restored, game)) == ["goal_highlight"]


def test_placeholder_penalty_waits_for_real_infraction() -> None:
    """Live STL@OTT 2026-10-13: a penalty showed descKey "minor" for one update, then "holding"."""
    game = FakeGame()
    game.start_period(1)
    det = EventDetector("BOS")
    step(det, game)

    pen_id = game.penalty("TOR", TOR_NYLANDER, desc="minor")
    assert step(det, game) == []
    restored = EventDetector("BOS", DetectorState.from_dict(det.state.as_dict()))
    assert restored.state.held == {pen_id: 1}

    game.amend(pen_id, descKey="holding", drawnByPlayerId=BOS_PASTA)
    (pen,) = step(restored, game)
    assert pen.type == "opponent_penalty"
    assert pen.data["infraction"] == "Holding"
    assert pen.data["drawn_by"]["name"] == "David Pastrnak"
    assert restored.state.held == {}


def test_placeholder_penalty_is_announced_after_waiting() -> None:
    game = FakeGame()
    game.start_period(1)
    det = EventDetector("BOS")
    step(det, game)
    game.penalty("BOS", BOS_MCAVOY, desc="minor")
    held = [step(det, game) for _ in range(MAX_PENALTY_HOLD_POLLS)]
    assert held == [[]] * MAX_PENALTY_HOLD_POLLS
    (pen,) = step(det, game)
    assert pen.type == "team_penalty"
    assert pen.data["infraction"] == "Minor"
    assert step(det, game) == []


def test_goal_updated_survives_restart_without_replaying() -> None:
    game = FakeGame()
    game.start_period(1)
    goal_id = game.goal("BOS", BOS_PASTA)
    det = EventDetector("BOS")
    step(det, game)  # baseline already includes the goal

    restored = EventDetector("BOS", DetectorState.from_dict(det.state.as_dict()))
    assert step(restored, game) == []
    game.amend(goal_id, assist1PlayerId=BOS_MCAVOY)
    assert types(step(restored, game)) == ["goal_updated"]


def test_goal_reversal_by_missing_play() -> None:
    game = FakeGame()
    game.start_period(1)
    det = EventDetector("BOS")
    step(det, game)
    goal_id = game.goal("BOS", BOS_PASTA)
    assert types(step(det, game)) == ["team_goal"]
    game.remove_play(goal_id, "BOS")
    (rev,) = step(det, game)
    assert rev.type == "goal_reversed"
    assert rev.data["side"] == "team"
    assert rev.data["score"] == {"team": 0, "opponent": 0}
    assert rev.data["scorer"]["name"] == "David Pastrnak"
    assert rev.data["original_period_label"] == "1st"


def test_score_drop_without_missing_play() -> None:
    game = FakeGame()
    game.start_period(1)
    game.goal("TOR", TOR_MATTHEWS)
    det = EventDetector("BOS")
    step(det, game)
    game.score["TOR"] = 0
    (rev,) = step(det, game)
    assert rev.type == "goal_reversed"
    assert rev.data["side"] == "opponent"


def test_away_team_perspective_and_overtime_loss() -> None:
    game = FakeGame(home="BOS", away="TOR")
    game.start_period(1)
    det = EventDetector("TOR")
    step(det, game)
    game.goal("BOS", BOS_PASTA)
    game.goal("TOR", TOR_MATTHEWS)
    events = step(det, game)
    assert types(events) == ["opponent_goal", "team_goal"]
    assert events[1].data["is_home"] is False
    assert events[1].data["score"] == {"team": 1, "opponent": 1}
    game.start_period(4, "OT")
    game.goal("BOS", BOS_PASTA)
    game.final("OT")
    events = step(det, game)
    assert types(events) == ["period_start", "opponent_goal", "game_end_otl"]
    assert events[1].data["period_label"] == "OT"


def test_baseline_mid_game_does_not_replay() -> None:
    game = FakeGame()
    game.start_period(1)
    game.goal("BOS", BOS_PASTA)
    game.goal("BOS", BOS_PASTA)
    det = EventDetector("BOS")
    assert step(det, game) == []
    assert step(det, game) == []


def test_baseline_after_final_is_silent() -> None:
    game = FakeGame()
    game.start_period(1)
    game.final()
    det = EventDetector("BOS")
    assert step(det, game) == []
    assert step(det, game) == []


def test_state_round_trip_resumes_without_replay() -> None:
    game = FakeGame()
    game.start_period(1)
    det = EventDetector("BOS")
    step(det, game)
    game.goal("BOS", BOS_PASTA)
    step(det, game)

    restored = EventDetector("BOS", DetectorState.from_dict(det.state.as_dict()))
    assert DetectorState.from_dict({"game_id": 1, "goals": {"5": "team"}}).goals == {5: {"side": "team"}}
    assert step(restored, game) == []
    game.goal("BOS", BOS_PASTA)
    assert types(step(restored, game)) == ["team_goal"]


def test_new_game_id_rebaselines() -> None:
    first = FakeGame(game_id=1)
    first.start_period(1)
    det = EventDetector("BOS")
    step(det, first)
    second = FakeGame(game_id=2)
    second.start_period(1)
    second.goal("BOS", BOS_PASTA)
    assert step(det, second) == []


def test_untracked_team_ignored() -> None:
    game = FakeGame()
    assert EventDetector("EDM").process(parse_play_by_play(game.play_by_play())) == []


def test_strength() -> None:
    # away goalie, away skaters, home skaters, home goalie
    assert strength_for("1551", True) == "ev"
    assert strength_for("1451", True) == "pp"
    assert strength_for("1451", False) == "sh"
    assert strength_for("0651", True) == "en"
    assert strength_for("1560", True) == "ev"  # home extra attacker, goalie pulled
    assert strength_for(None, True) is None
    assert strength_for("15", True) is None


def test_period_label() -> None:
    assert period_label(1, "REG") == "1st"
    assert period_label(3, "REG") == "3rd"
    assert period_label(4, "OT") == "OT"
    assert period_label(5, "OT") == "2OT"
    assert period_label(5, "SO") == "SO"
    assert period_label(None, None) is None
