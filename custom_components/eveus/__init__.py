"""The Eveus integration."""
from __future__ import annotations
import logging
from typing import Dict, Any
import asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from .const import DOMAIN

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER]
_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
   """Set up Eveus component."""
   hass.data.setdefault(DOMAIN, {})
   return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
   """Set up Eveus from config entry."""
   try:
       hass.data.setdefault(DOMAIN, {})
       hass.data[DOMAIN][entry.entry_id] = {
           "title": entry.title,
           "options": entry.options.copy(), 
           "entities": {},
           "cleanup_tasks": set()
       }
       
       # Use new async_forward_entry_setups instead of async_forward_entry_setup
       async with asyncio.timeout(30):
           await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
           
       return True
       
   except asyncio.TimeoutError:
       _LOGGER.error("Timeout setting up Eveus integration")
       await cleanup_resources(hass, entry)
       raise ConfigEntryNotReady
       
   except Exception as ex:
       _LOGGER.error("Error setting up Eveus integration: %s", str(ex))
       await cleanup_resources(hass, entry)
       raise ConfigEntryNotReady from ex

async def cleanup_resources(hass: HomeAssistant, entry: ConfigEntry) -> None:
   """Clean up resources."""
   tasks = hass.data[DOMAIN][entry.entry_id].get("cleanup_tasks", set())
   if tasks:
       await asyncio.gather(*tasks, return_exceptions=True)
       tasks.clear()

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
   """Unload config entry."""
   try:
       async with asyncio.timeout(30):
           unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
           if unload_ok:
               await cleanup_resources(hass, entry)
               hass.data[DOMAIN].pop(entry.entry_id)
           return unload_ok
           
   except asyncio.TimeoutError:
       _LOGGER.error("Timeout unloading integration")
       return False
       
   except Exception as ex:
       _LOGGER.error("Error unloading integration: %s", str(ex))
       return False
