"""The Eveus integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .common import EveusUpdater, send_eveus_command  # Add missing import

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
        # Initialize data structure
        hass.data.setdefault(DOMAIN, {})
        
        # Create updater instance
        updater = EveusUpdater(
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            hass=hass,
        )

        # Store entry data with credentials needed for platforms
        hass.data[DOMAIN][entry.entry_id] = {
            "title": entry.title,
            "updater": updater,
            "host": entry.data[CONF_HOST],  # Added
            "username": entry.data[CONF_USERNAME],  # Added
            "password": entry.data[CONF_PASSWORD],  # Added
            "entities": {},
        }

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    except Exception as ex:
        _LOGGER.error("Error setting up Eveus integration: %s", str(ex), exc_info=True)
        raise ConfigEntryNotReady from ex

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        # Get updater instance
        data = hass.data[DOMAIN].get(entry.entry_id, {})
        updater = data.get("updater")

        # Unload platforms
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        
        if unload_ok and updater:
            # Shutdown updater
            await updater.async_shutdown()
            hass.data[DOMAIN].pop(entry.entry_id)
        
        return unload_ok

    except Exception as ex:
        _LOGGER.error("Error unloading Eveus integration: %s", str(ex))
        return False
