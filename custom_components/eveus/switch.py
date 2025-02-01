# File: custom_components/eveus/__init__.py
"""The Eveus integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .base import EveusBaseConnection
from .exceptions import EveusConnectionError

PLATFORMS = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
]

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Eveus component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eveus from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    try:
        # Create and validate connection
        connection = EveusBaseConnection(
            host=entry.data["host"],
            username=entry.data["username"],
            password=entry.data["password"],
        )
        
        # Test connection by attempting update
        await connection.async_update()
        
        # Store entry data
        hass.data[DOMAIN][entry.entry_id] = {
            "title": entry.title,
            "connection": connection,
            "entities": {},
        }

        # Set up platforms with forward entry setups
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    except EveusConnectionError as err:
        _LOGGER.error("Error connecting to Eveus device: %s", str(err))
        raise ConfigEntryNotReady from err
    except Exception as ex:
        _LOGGER.error("Unexpected error setting up Eveus integration: %s", str(ex))
        raise ConfigEntryNotReady from ex

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        # Unload platforms
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        
        if unload_ok:
            # Close connection and clean up
            connection = hass.data[DOMAIN][entry.entry_id].get("connection")
            if connection:
                await connection.async_close()
            hass.data[DOMAIN].pop(entry.entry_id)
            
        return unload_ok

    except Exception as ex:
        _LOGGER.error("Error unloading Eveus integration: %s", str(ex))
        return False
