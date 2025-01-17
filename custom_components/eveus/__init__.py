"""The Eveus integration for Home Assistant."""
from __future__ import annotations

import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Eveus component from YAML configuration (not supported)."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eveus from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    try:
        # Initialize integration data structure
        hass.data[DOMAIN][entry.entry_id] = {
            "title": entry.title,
            "options": entry.options.copy(),
            "entities": {
                "sensor": {},
                "switch": {},
                "number": {},
            },
            "updaters": {},
        }

        # Load platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))
        return True

    except Exception as ex:
        _LOGGER.error("Error setting up Eveus integration: %s", str(ex))
        raise ConfigEntryNotReady from ex

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        # Unload platforms
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        
        # Clean up resources
        if unload_ok:
            # Get updaters and shut them down
            updaters = hass.data[DOMAIN][entry.entry_id].get("updaters", {})
            for updater in updaters.values():
                await updater.async_shutdown()
            
            # Remove entry data
            hass.data[DOMAIN].pop(entry.entry_id)
            
        return unload_ok

    except Exception as ex:
        _LOGGER.error("Error unloading Eveus integration: %s", str(ex))
        return False

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
