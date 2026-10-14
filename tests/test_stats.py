"""Team stats computed from play-by-play."""

from __future__ import annotations

from fake_nhl import FakeGame

from custom_components.nhl_companion.parser import parse_play_by_play
from custom_components.nhl_companion.stats import game_stats

PASTA, MCAVOY, GEEKIE = 8477956, 8479325, 8482072
MATTHEWS, NYLANDER, RIELLY = 8479318, 8477939, 8476853


def test_game_stats() -> None:
    game = FakeGame()
    game.start_period(1)
    game.faceoff("BOS", GEEKIE, MATTHEWS)
    game.faceoff("BOS", GEEKIE, MATTHEWS)
    game.faceoff("TOR", MATTHEWS, GEEKIE)
    game.hit("BOS", MCAVOY, NYLANDER)
    game.hit("TOR", RIELLY, PASTA)
    game.hit("TOR", RIELLY, PASTA)
    # Owned by the shooting team: credited to the blocker's team
    game.blocked_shot("TOR", MATTHEWS, MCAVOY)
    # Blocked by a teammate: not a block
    game.blocked_shot("TOR", MATTHEWS, RIELLY)
    game.penalty("TOR", NYLANDER, PASTA, minutes=2)
    game.shot("BOS", PASTA)
    game.goal("BOS", PASTA, MCAVOY, situation="1451", time_in_period="10:00")
    game.goal("TOR", MATTHEWS, time_in_period="12:00")

    snap = parse_play_by_play(game.play_by_play())
    team, opp, _ = snap.game.side_for("BOS")
    stats = game_stats(snap, team, opp)

    assert stats["team"] == {
        "shots_on_goal": 2,
        "hits": 1,
        "blocked_shots": 1,
        "faceoff_wins": 2,
        "faceoff_pct": 66.7,
        "giveaways": 0,
        "takeaways": 0,
        "penalty_minutes": 0,
        "power_play_goals": 1,
    }
    assert stats["opponent"]["hits"] == 2
    assert stats["opponent"]["blocked_shots"] == 0
    assert stats["opponent"]["penalty_minutes"] == 2
    assert stats["opponent"]["faceoff_pct"] == 33.3
    assert stats["goals"] == [
        {
            "side": "team",
            "period_label": "1st",
            "time_in_period": "10:00",
            "scorer": "David Pastrnak",
            "assists": ["Charlie McAvoy"],
            "strength": "pp",
            "score": {"team": 1, "opponent": 0},
        },
        {
            "side": "opponent",
            "period_label": "1st",
            "time_in_period": "12:00",
            "scorer": "Auston Matthews",
            "assists": [],
            "strength": "ev",
            "score": {"team": 1, "opponent": 1},
        },
    ]


def test_game_stats_from_away_side() -> None:
    game = FakeGame()
    game.start_period(1)
    game.goal("TOR", MATTHEWS)
    snap = parse_play_by_play(game.play_by_play())
    team, opp, _ = snap.game.side_for("TOR")
    stats = game_stats(snap, team, opp)
    assert stats["goals"][0]["side"] == "team"
    assert stats["goals"][0]["score"] == {"team": 1, "opponent": 0}
    assert stats["team"]["faceoff_pct"] is None
