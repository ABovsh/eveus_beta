"""The Eveus integration."""
from __future__ import annotations
import logging
from typing import Any
import asyncio
from functools import partial

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
   hass.data.setdefault(DOMAIN, {})
   
   try:
       # Initialize entry data
       hass.data[DOMAIN][entry.entry_id] = {
           "title": entry.title,
           "options": entry.options.copy(),
           "entities": {},
           "cleanup_tasks": set()
       }

       # Forward setup to platforms
       await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

       return True

   except Exception as ex:
       _LOGGER.error("Error setting up Eveus integration: %s", str(ex))
       await cleanup_resources(hass, entry)
       raise ConfigEntryNotReady from ex

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
   """Unload config entry."""
   try:
       unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
       if unload_ok:
           await cleanup_resources(hass, entry)
           hass.data[DOMAIN].pop(entry.entry_id)
       return unload_ok

   except Exception as ex:
       _LOGGER.error("Error unloading Eveus integration: %s", str(ex))
       return False

async def cleanup_resources(hass: HomeAssistant, entry: ConfigEntry) -> None:
   """Clean up resources."""
   entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
   cleanup_tasks = entry_data.get("cleanup_tasks", set())

   if cleanup_tasks:
       _LOGGER.debug("Running cleanup for entry %s", entry.entry_id)
       await asyncio.gather(*cleanup_tasks, return_exceptions=True)
       cleanup_tasks.clear()
