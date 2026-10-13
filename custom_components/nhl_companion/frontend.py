"""Serve and auto-register the bundled Lovelace cards."""

from __future__ import annotations

from contextlib import suppress
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)

CARDS_URL_BASE = f"/{DOMAIN}_static"
CARDS_FILE = "nhl-companion-cards.js"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Expose www/ and load the card bundle on every dashboard."""
    www = Path(__file__).parent / "www"
    if hass.http is None or "frontend" not in hass.config.components:
        _LOGGER.debug("Frontend not loaded, skipping card registration")
        return
    if not await hass.async_add_executor_job((www / CARDS_FILE).is_file):
        _LOGGER.warning("Card bundle missing at %s", www / CARDS_FILE)
        return
    # RuntimeError means the path is already registered
    with suppress(RuntimeError):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARDS_URL_BASE, str(www), cache_headers=False)]
        )
    add_extra_js_url(hass, f"{CARDS_URL_BASE}/{CARDS_FILE}?v={VERSION}")
