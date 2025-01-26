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
        
    async def async_setup(self, config: dict) -> bool:
        """Set up integration from configuration."""
        self.hass.data.setdefault(DOMAIN, {})
        return True

    async def async_setup_entry(self, entry: ConfigEntry) -> bool:
        """Set up from config entry."""
        try:
            # Initialize entry data structure
            self.hass.data.setdefault(DOMAIN, {})
            self.hass.data[DOMAIN][entry.entry_id] = {
                "title": entry.title,
                "options": entry.options.copy(),
                "entities": {},
                "cleanup_tasks": set()
            }

            # Load platforms
            async with asyncio.timeout(30):
                await self.hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
                return True

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout setting up Eveus integration")
            await self.cleanup_resources(entry)
            raise ConfigEntryNotReady
        
        except Exception as err:
            await self.handle_error(err, "Error setting up integration")
            await self.cleanup_resources(entry)
            raise ConfigEntryNotReady from err

    async def cleanup_resources(self, entry: ConfigEntry) -> None:
        """Clean up integration resources."""
        try:
            tasks = self.hass.data[DOMAIN][entry.entry_id].get("cleanup_tasks", set())
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks.clear()
        except Exception as err:
            await self.handle_error(err, "Error cleaning up resources")

    async def async_unload_entry(self, entry: ConfigEntry) -> bool:
        """Unload config entry."""
        try:
            async with asyncio.timeout(30):
                unload_ok = await self.hass.config_entries.async_unload_platforms(entry, PLATFORMS)
                if unload_ok:
                    await self.cleanup_resources(entry)
                    self.hass.data[DOMAIN].pop(entry.entry_id)
                return unload_ok

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout unloading integration")
            return False
            
        except Exception as err:
            await self.handle_error(err, "Error unloading integration")
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
