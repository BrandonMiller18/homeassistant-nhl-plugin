"""Install the bundled blueprints into the Home Assistant config."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

BUNDLED = Path(__file__).parent / "blueprints"


def _sync(source: Path, target: Path) -> list[str]:
    """Copy blueprints that are missing or differ, return their relative paths."""
    changed = []
    for src in sorted(source.glob("*/*.yaml")):
        rel = f"{src.parent.name}/{DOMAIN}/{src.name}"
        dest = target / rel
        content = src.read_bytes()
        if dest.is_file() and dest.read_bytes() == content:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        changed.append(rel)
    return changed


async def async_install_blueprints(hass: HomeAssistant) -> list[str]:
    """Bring /config/blueprints/<domain>/nhl_companion in line with this release.

    The installed files are managed: local edits are overwritten on the next start.
    """
    try:
        changed = await hass.async_add_executor_job(_sync, BUNDLED, Path(hass.config.path("blueprints")))
    except OSError as err:
        _LOGGER.warning("Could not install the bundled blueprints: %s", err)
        return []
    if changed:
        _LOGGER.info("Installed or updated blueprints: %s", ", ".join(changed))
        # Automations already loaded keep the old blueprint until reloaded
        for domain in {rel.split("/")[0] for rel in changed}:
            if domain in hass.config.components and hass.services.has_service(domain, "reload"):
                hass.async_create_task(hass.services.async_call(domain, "reload"))
    return changed
