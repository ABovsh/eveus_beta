"""The Eveus integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .common import EveusUpdater, EveusConnectionError

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
    """Set up Eveus from a config entry with improved error handling."""
    try:
        # Initialize data structure
        hass.data.setdefault(DOMAIN, {})
        
        # Test connection before creating updater
        session = async_get_clientsession(hass)
        try:
            async with session.post(
                f"http://{entry.data[CONF_HOST]}/main",
                auth=aiohttp.BasicAuth(
                    entry.data[CONF_USERNAME],
                    entry.data[CONF_PASSWORD]
                ),
                timeout=5
            ) as response:
                response.raise_for_status()
                
        except Exception as err:
            _LOGGER.error("Connection test failed: %s", str(err))
            raise ConfigEntryNotReady("Failed to connect to device") from err
        
        # Create updater instance
        updater = EveusUpdater(
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            hass=hass,
        )

        # Store entry data
        hass.data[DOMAIN][entry.entry_id] = {
            "title": entry.title,
            "updater": updater,
            "host": entry.data[CONF_HOST],
            "username": entry.data[CONF_USERNAME],
            "password": entry.data[CONF_PASSWORD],
            "entities": {},
        }

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        return True

    except EveusConnectionError as err:
        _LOGGER.error("Failed to connect to Eveus device: %s", str(err))
        raise ConfigEntryNotReady from err
        
    except Exception as ex:
        _LOGGER.error(
            "Error setting up Eveus integration: %s", 
            str(ex), 
            exc_info=True
        )
        raise ConfigEntryNotReady from ex

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry with proper cleanup."""
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
        _LOGGER.error(
            "Error unloading Eveus integration: %s", 
            str(ex),
            exc_info=True
        )
        return False
