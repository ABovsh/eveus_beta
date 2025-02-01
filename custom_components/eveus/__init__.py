"""The Eveus integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api.client import EveusClient
from .api.models import DeviceInfo
from .const import DOMAIN

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
    try:
        device_info = DeviceInfo(
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            model=entry.data.get("model", "16A")
        )
        
        client = EveusClient(device_info)
        await client.update()  # Test connection
        
        hass.data[DOMAIN][entry.entry_id] = {
            "client": client,
            "device_info": device_info
        }
        
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    except Exception as ex:
        _LOGGER.error("Error setting up Eveus integration: %s", str(ex))
        raise ConfigEntryNotReady from ex

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        if unload_ok:
            client = hass.data[DOMAIN][entry.entry_id]["client"]
            await client.close()
            hass.data[DOMAIN].pop(entry.entry_id)
        return unload_ok
    except Exception as ex:
        _LOGGER.error("Error unloading Eveus integration: %s", str(ex))
        return False
