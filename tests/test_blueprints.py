"""Bundled blueprints: valid, installed into the config, kept in sync, versioned."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.components.blueprint.models import Blueprint
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.core import HomeAssistant
from homeassistant.util.yaml import load_yaml_dict
import pytest

from custom_components.nhl_companion.blueprints import BUNDLED, async_install_blueprints
from custom_components.nhl_companion.const import DOMAIN, VERSION

COMPONENT = BUNDLED.parent
SOURCES = sorted(BUNDLED.glob("*/*.yaml"))
REPO_URL = "https://github.com/BrandonMiller18/homeassistant-nhl-plugin/blob/main/"


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_bundled_blueprint_is_valid(path: Path) -> None:
    blueprint = Blueprint(
        load_yaml_dict(str(path)), expected_domain=path.parent.name, schema=BLUEPRINT_SCHEMA
    )
    rel = path.relative_to(COMPONENT.parent.parent).as_posix()
    assert blueprint.metadata["source_url"] == REPO_URL + rel


async def test_install_and_resync(hass: HomeAssistant, tmp_path: Path) -> None:
    hass.config.config_dir = str(tmp_path)
    installed = tmp_path / "blueprints" / "automation" / DOMAIN

    assert len(await async_install_blueprints(hass)) == len(SOURCES)
    for src in SOURCES:
        assert (installed / src.name).read_bytes() == src.read_bytes()

    # Nothing changed: nothing rewritten
    assert await async_install_blueprints(hass) == []

    # A local edit is overwritten, other blueprints are left alone
    (installed / "goal_lights.yaml").write_text("edited")
    other = tmp_path / "blueprints" / "automation" / "someone_else" / "mine.yaml"
    other.parent.mkdir(parents=True)
    other.write_text("keep me")
    assert await async_install_blueprints(hass) == [f"automation/{DOMAIN}/goal_lights.yaml"]
    restored = (installed / "goal_lights.yaml").read_bytes()
    assert restored == (BUNDLED / "automation" / "goal_lights.yaml").read_bytes()
    assert other.read_text() == "keep me"


def test_versions_match() -> None:
    """The release workflow tags from manifest.json; the card cache-buster uses const.VERSION."""
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert manifest["version"] == VERSION
