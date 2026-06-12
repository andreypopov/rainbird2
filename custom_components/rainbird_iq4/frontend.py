"""Frontend support for Rain Bird IQ4."""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import CARD_FILENAME, DATA_FRONTEND_REGISTERED, DOMAIN, FRONTEND_URL_PATH


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Register static files for the bundled Lovelace card."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(DATA_FRONTEND_REGISTERED):
        return

    card_path = Path(__file__).parent / "www" / CARD_FILENAME
    try:
        from homeassistant.components.http import StaticPathConfig
    except ImportError:
        hass.http.register_static_path(f"{FRONTEND_URL_PATH}/{CARD_FILENAME}", str(card_path), True)
    else:
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    f"{FRONTEND_URL_PATH}/{CARD_FILENAME}",
                    str(card_path),
                    True,
                )
            ]
        )

    domain_data[DATA_FRONTEND_REGISTERED] = True

