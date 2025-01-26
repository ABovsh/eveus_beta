"""The Eveus integration."""
from __future__ import annotations

import logging
import asyncio
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .mixins import ErrorHandlingMixin, ValidationMixin

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER]
_LOGGER = logging.getLogger(__name__)

class EveusIntegrationHandler(ErrorHandlingMixin, ValidationMixin):
    """Handle Eveus integration setup and cleanup."""

    def __init__(self, hass: HomeAssistant):
        """Initialize handler."""
        self.hass = hass
        self._setup_lock = asyncio.Lock()
        
    async def async_setup(self, config: dict) -> bool:
        """Set up integration from configuration."""
        self.hass.data.setdefault(DOMAIN, {})
        return True

    async def async_setup_entry(self, entry: ConfigEntry) -> bool:
        """Set up Eveus from config entry."""
        async with self._setup_lock:
            try:
                # Check if already set up
                if entry.entry_id in self.hass.data.get(DOMAIN, {}):
                    _LOGGER.warning("Config entry %s has already been setup!", entry.entry_id)
                    return False

                # Initialize entry data structure
                self.hass.data.setdefault(DOMAIN, {})
                self.hass.data[DOMAIN][entry.entry_id] = {
                    "title": entry.title,
                    "options": entry.options.copy(),
                    "entities": {},
                    "cleanup_tasks": set()
                }

                # Set up platforms using the new method
                await self.hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
                return True

            except asyncio.TimeoutError as ex:
                _LOGGER.error("Timeout setting up Eveus integration")
                await self.cleanup_resources(entry)
                raise ConfigEntryNotReady from ex

            except Exception as ex:
                _LOGGER.error("Error setting up Eveus integration: %s", str(ex))
                await self.cleanup_resources(entry)
                raise ConfigEntryNotReady from ex

    async def cleanup_resources(self, entry: ConfigEntry) -> None:
        """Clean up integration resources."""
        if DOMAIN not in self.hass.data or entry.entry_id not in self.hass.data[DOMAIN]:
            return

        tasks = self.hass.data[DOMAIN][entry.entry_id].get("cleanup_tasks", set())
        if tasks:
            try:
                async with asyncio.timeout(10):
                    await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as ex:
                _LOGGER.error("Error during cleanup: %s", str(ex))
            finally:
                tasks.clear()

    async def async_unload_entry(self, entry: ConfigEntry) -> bool:
        """Unload config entry."""
        try:
            unload_ok = await self.hass.config_entries.async_unload_platforms(entry, PLATFORMS)
            if unload_ok:
                await self.cleanup_resources(entry)
                self.hass.data[DOMAIN].pop(entry.entry_id)
            return unload_ok
            
        except Exception as ex:
            _LOGGER.error("Error unloading integration: %s", str(ex))
            return False

# Global integration handler instance
_HANDLER: EveusIntegrationHandler | None = None

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Eveus component."""
    global _HANDLER
    _HANDLER = EveusIntegrationHandler(hass)
    return await _HANDLER.async_setup(config)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eveus from config entry."""
    return await _HANDLER.async_setup_entry(entry)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry."""
    return await _HANDLER.async_unload_entry(entry)
