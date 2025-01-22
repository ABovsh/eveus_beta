"""The Eveus integration."""
from __future__ import annotations

import asyncio
import logging
import importlib
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
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    HELPER_EV_BATTERY_CAPACITY,
    HELPER_EV_INITIAL_SOC,
    HELPER_EV_SOC_CORRECTION,
    HELPER_EV_TARGET_SOC,
    UPDATE_INTERVAL_IDLE,
)
from .session_manager import SessionManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eveus from a config entry."""
    try:
        # Load platform modules in executor to avoid blocking
        platform_modules = {}
        for platform in PLATFORMS:
            try:
                module_name = f"custom_components.eveus.{platform}"
                module = await hass.async_add_executor_job(
                    importlib.import_module, module_name
                )
                platform_modules[platform] = module
            except ImportError as err:
                _LOGGER.error(
                    "Error importing platform %s: %s",
                    platform,
                    str(err)
                )
                continue

        session_manager = SessionManager(
            hass=hass,
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            entry_id=entry.entry_id,
        )

        try:
            await session_manager.initialize()
        except Exception as err:
            await session_manager.close()
            _LOGGER.error("Failed to initialize session manager: %s", str(err))
            raise ConfigEntryNotReady from err

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "session_manager": session_manager,
            "title": entry.title,
            "options": entry.options.copy(),
            "entities": {platform: {} for platform in PLATFORMS},
        }

        # Forward entry setup using loaded modules
        for platform in PLATFORMS:
            if platform in platform_modules:
                try:
                    if hasattr(platform_modules[platform], "async_setup_entry"):
                        await platform_modules[platform].async_setup_entry(hass, entry)
                except Exception as err:
                    _LOGGER.error(
                        "Error setting up platform %s: %s",
                        platform,
                        str(err)
                    )

        # Set up periodic updates
        async def async_update(now=None):
            """Update device state."""
            try:
                await session_manager.async_update()
            except Exception as err:
                _LOGGER.error("Error updating device: %s", str(err))

        entry.async_on_unload(
            async_track_time_interval(
                hass,
                async_update,
                UPDATE_INTERVAL_IDLE
            )
        )

        return True

    except Exception as err:
        _LOGGER.error("Error setting up Eveus integration: %s", str(err))
        raise ConfigEntryNotReady from err
