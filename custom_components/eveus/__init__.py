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

class IntegrationSetupError(Exception):
    """Base class for integration setup errors."""

class PlatformSetupError(IntegrationSetupError):
    """Error occurred during platform setup."""

class EveusIntegrationHandler(ErrorHandlingMixin, ValidationMixin):
    """Handle Eveus integration setup and cleanup."""

    def __init__(self, hass: HomeAssistant):
        """Initialize handler."""
        self.hass = hass
        self._setup_lock = asyncio.Lock()
        self._platform_tasks = {}
        
    async def async_setup(self, config: dict) -> bool:
        """Set up integration from configuration."""
        self.hass.data.setdefault(DOMAIN, {})
        return True

    async def _setup_platform(self, entry: ConfigEntry, platform: Platform) -> None:
        """Set up single platform with error handling."""
        try:
            async with asyncio.timeout(30):
                await self.hass.config_entries.async_forward_entry_setup(entry, platform)
                self._platform_tasks[platform] = None
        except Exception as err:
            self._platform_tasks[platform] = err
            raise PlatformSetupError(f"Failed to set up {platform}: {str(err)}") from err

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

                # Set up platforms concurrently with proper error handling
                setup_tasks = []
                for platform in PLATFORMS:
                    task = asyncio.create_task(
                        self._setup_platform(entry, platform),
                        name=f"setup_{platform}"
                    )
                    setup_tasks.append(task)

                # Wait for all platforms to set up
                try:
                    async with asyncio.timeout(60):  # Global setup timeout
                        await asyncio.gather(*setup_tasks)
                    return True
                except asyncio.TimeoutError:
                    _LOGGER.error("Integration setup timed out")
                    await self._cleanup_failed_setup(entry, setup_tasks)
                    raise ConfigEntryNotReady
                except Exception as err:
                    _LOGGER.error("Error during platform setup: %s", str(err))
                    await self._cleanup_failed_setup(entry, setup_tasks)
                    raise ConfigEntryNotReady from err

            except Exception as err:
                _LOGGER.error("Failed to set up integration: %s", str(err))
                await self.cleanup_resources(entry)
                raise ConfigEntryNotReady from err

    async def _cleanup_failed_setup(self, entry: ConfigEntry, setup_tasks: list) -> None:
        """Clean up after failed setup."""
        # Cancel any pending setup tasks
        for task in setup_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to cancel
        await asyncio.gather(*setup_tasks, return_exceptions=True)
        
        # Unload any successfully loaded platforms
        for platform in PLATFORMS:
            if platform in self._platform_tasks and self._platform_tasks[platform] is None:
                try:
                    await self.hass.config_entries.async_forward_entry_unload(entry, platform)
                except Exception as err:
                    _LOGGER.error("Error unloading platform %s: %s", platform, str(err))

        # Clean up resources
        await self.cleanup_resources(entry)

    async def cleanup_resources(self, entry: ConfigEntry) -> None:
        """Clean up integration resources."""
        if DOMAIN not in self.hass.data or entry.entry_id not in self.hass.data[DOMAIN]:
            return

        # Clean up tasks
        tasks = self.hass.data[DOMAIN][entry.entry_id].get("cleanup_tasks", set())
        if tasks:
            try:
                async with asyncio.timeout(10):
                    done, pending = await asyncio.wait(tasks)
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    for task in done:
                        try:
                            await task
                        except Exception as ex:
                            _LOGGER.error("Error during cleanup task: %s", str(ex))
            except asyncio.TimeoutError:
                _LOGGER.error("Cleanup tasks timed out")
            except Exception as ex:
                _LOGGER.error("Error during cleanup: %s", str(ex))
            finally:
                tasks.clear()

    async def async_unload_entry(self, entry: ConfigEntry) -> bool:
        """Unload config entry."""
        try:
            # Unload platforms with timeout
            async with asyncio.timeout(30):
                unload_ok = True
                for platform in PLATFORMS:
                    try:
                        if unload_ok:
                            unload_ok = await self.hass.config_entries.async_forward_entry_unload(
                                entry, platform
                            )
                    except Exception as ex:
                        _LOGGER.error("Error unloading platform %s: %s", platform, str(ex))
                        unload_ok = False

                if unload_ok:
                    # Final cleanup
                    await self.cleanup_resources(entry)
                    self.hass.data[DOMAIN].pop(entry.entry_id)

                return unload_ok

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout unloading integration")
            return False
            
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
