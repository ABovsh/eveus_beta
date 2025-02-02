"""The Eveus integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .common import EveusUpdater, send_eveus_command

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Eveus component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eveus from a config entry."""
    try:
        host = entry.data[CONF_HOST]
        username = entry.data[CONF_USERNAME]
        password = entry.data[CONF_PASSWORD]

        updater = EveusUpdater(
            hass=hass,
            host=host,
            username=username,
            password=password,
            update_interval=30  # seconds
        )

        await updater.async_init()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "updater": updater,
            "host": host,
            "username": username,
            "password": password,
        }

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    except Exception as err:
        _LOGGER.error("Error setting up Eveus integration: %s", str(err))
        raise ConfigEntryNotReady from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data = hass.data[DOMAIN].pop(entry.entry_id)
        if updater := data.get("updater"):
            await updater.async_shutdown()

    return unload_ok
