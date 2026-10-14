"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from fake_nhl import FakeGame, club_schedule, league_schedule, standings

from custom_components.nhl_companion.parser import (
    parse_club_schedule,
    parse_play_by_play,
    parse_schedule,
    parse_standings,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom_components in every test."""
    return


class FakeApi:
    """Drives NhlApiClient methods from a FakeGame."""

    def __init__(self, game: FakeGame) -> None:
        self.game = game

    async def get_team_schedule(self, abbrev):
        return parse_club_schedule(club_schedule(abbrev, [self.game]))

    async def get_play_by_play(self, game_id):
        return parse_play_by_play(self.game.play_by_play())

    async def get_schedule(self, date=None):
        return parse_schedule(league_schedule([self.game]))

    async def get_standings(self):
        return parse_standings(standings())

    async def get_three_stars(self, game_id):
        return self.three_stars

    three_stars: list = []


@pytest.fixture
def fake_game() -> FakeGame:
    """A BOS vs TOR game starting in two hours."""
    return FakeGame()


@pytest.fixture
def mock_api(fake_game: FakeGame) -> Generator[FakeApi]:
    """Patch the API client to serve the fake game."""
    api = FakeApi(fake_game)
    target = "custom_components.nhl_companion.api.NhlApiClient"
    with (
        patch(f"{target}.get_team_schedule", side_effect=api.get_team_schedule),
        patch(f"{target}.get_play_by_play", side_effect=api.get_play_by_play),
        patch(f"{target}.get_schedule", side_effect=api.get_schedule),
        patch(f"{target}.get_standings", side_effect=api.get_standings),
        patch(f"{target}.get_three_stars", side_effect=api.get_three_stars),
    ):
        yield api
