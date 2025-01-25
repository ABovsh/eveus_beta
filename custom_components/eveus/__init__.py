"""The Eveus integration."""
from __future__ import annotations
import logging
import asyncio
from typing import Dict, Any
from homeassistant.config_entries import ConfigEntry 
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER]
_LOGGER = logging.getLogger(__name__)

def _import_platforms() -> Dict[Platform, Any]:
    """Import platform modules synchronously."""
    # Import here to avoid circular dependencies
    from . import sensor, switch, number
    return {
        Platform.SENSOR: sensor,
        Platform.SWITCH: switch,
        Platform.NUMBER: number
    }

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Eveus component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eveus from config entry."""
    try:
        # Initialize data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "title": entry.title,
            "options": entry.options.copy(),
            "entities": {},
            "cleanup_tasks": set()
        }

        # Import platforms in executor to avoid blocking
        platforms = await hass.async_add_executor_job(_import_platforms)
        
        # Set up each platform 
        for platform, module in platforms.items():
            try:
                if hasattr(module, "async_setup_entry"):
                    await module.async_setup_entry(hass, entry)
            except Exception as platform_ex:
                _LOGGER.error("Error setting up %s platform: %s", platform, str(platform_ex))
                raise

        return True

    except Exception as ex:
        _LOGGER.error("Error setting up Eveus integration: %s", str(ex))
        await cleanup_resources(hass, entry)
        raise ConfigEntryNotReady from ex

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry with proper cleanup."""
    try:
        # Unload platforms
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        
        if unload_ok:
            # Clean up resources and remove entry data
            await cleanup_resources(hass, entry)
            hass.data[DOMAIN].pop(entry.entry_id)
            
        return unload_ok

    except Exception as ex:
        _LOGGER.error("Error unloading Eveus integration: %s", str(ex))
        return False

async def cleanup_resources(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up integration resources properly."""
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    cleanup_tasks = entry_data.get("cleanup_tasks", set())
    
    if cleanup_tasks:
        # Run all cleanup tasks concurrently
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        cleanup_tasks.clear()
