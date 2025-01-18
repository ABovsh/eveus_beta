"""The Eveus integration."""
from __future__ import annotations

import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, UPDATE_INTERVAL
from .session_manager import SessionManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final = [
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
        # Initialize session manager
        session_manager = SessionManager(
            hass=hass,
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            entry_id=entry.entry_id,
        )

        # Test connection and get initial state
        try:
            initial_state = await session_manager.get_state()
            
            # Update entry data with firmware and station ID if needed
            data_update = {}
            if "verFWMain" in initial_state:
                data_update["firmware_version"] = initial_state["verFWMain"].strip()
            if "stationId" in initial_state:
                data_update["station_id"] = initial_state["stationId"].strip()
                
            if data_update:
                hass.config_entries.async_update_entry(
                    entry, 
                    data={**entry.data, **data_update}
                )
                
        except Exception as err:
            await session_manager.close()
            _LOGGER.error("Connection failed: %s", str(err))
            raise ConfigEntryNotReady from err

        # Store session manager and initialize data structure
        hass.data[DOMAIN][entry.entry_id] = {
            "session_manager": session_manager,
            "title": entry.title,
            "options": entry.options.copy(),
            "entities": {
                "sensor": {},
                "switch": {},
                "number": {},
            },
        }

        # Forward to platform setup
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Register update listener
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))

        return True

    except Exception as err:
        _LOGGER.error("Error setting up Eveus integration: %s", str(err))
        raise ConfigEntryNotReady from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        # Unload platforms
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

        if unload_ok:
            # Get session manager and close it
            session_manager = hass.data[DOMAIN][entry.entry_id].get("session_manager")
            if session_manager:
                await session_manager.close()

            # Remove entry data
            hass.data[DOMAIN].pop(entry.entry_id)

        return unload_ok
    except Exception as err:
        _LOGGER.error("Error unloading entry: %s", str(err))
        return False

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
