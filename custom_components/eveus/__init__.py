"""The Eveus integration."""
from __future__ import annotations

import logging
from functools import partial
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
from homeassistant.helpers.storage import Store
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    HELPER_EV_BATTERY_CAPACITY,
    HELPER_EV_INITIAL_SOC,
    HELPER_EV_SOC_CORRECTION,
    HELPER_EV_TARGET_SOC,
)
from .session_manager import SessionManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
]

REQUIRED_HELPERS = {
    HELPER_EV_BATTERY_CAPACITY: (10, 160),  # kWh
    HELPER_EV_INITIAL_SOC: (0, 100),  # %
    HELPER_EV_SOC_CORRECTION: (0, 10),  # %
    HELPER_EV_TARGET_SOC: (0, 100),  # %
}

async def async_validate_helper_entities(hass: HomeAssistant) -> tuple[bool, list[str]]:
    """Validate required helper entities."""
    missing_helpers = []
    for helper_id, (min_val, max_val) in REQUIRED_HELPERS.items():
        state = hass.states.get(helper_id)
        if not state:
            missing_helpers.append(f"Missing helper: {helper_id}")
            continue
           
        try:
            value = float(state.state)
            if not min_val <= value <= max_val:
                missing_helpers.append(
                    f"{helper_id}: Value {value} outside range [{min_val}, {max_val}]"
                )
        except (ValueError, TypeError):
            missing_helpers.append(
                f"{helper_id}: Invalid value '{state.state}'"
            )
           
    return len(missing_helpers) == 0, missing_helpers

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Eveus component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eveus from a config entry."""
    try:
        # Validate helper entities
        valid_helpers, missing = await async_validate_helper_entities(hass)
        if not valid_helpers:
            error_msg = f"Missing or invalid helper entities: {', '.join(missing)}"
            _LOGGER.error(error_msg)
            raise ConfigEntryNotReady(error_msg)

        # Initialize session manager in the executor
        try:
            session_manager = await hass.async_add_executor_job(
                partial(
                    SessionManager,
                    hass=hass,
                    host=entry.data[CONF_HOST],
                    username=entry.data[CONF_USERNAME],
                    password=entry.data[CONF_PASSWORD],
                    entry_id=entry.entry_id,
                )
            )
        except Exception as err:
            _LOGGER.error("Failed to create session manager: %s", str(err))
            raise ConfigEntryNotReady(f"Session manager initialization failed: {err}") from err

        try:
            await session_manager.initialize()
        except Exception as err:
            _LOGGER.error("Failed to initialize session manager: %s", str(err))
            await session_manager.close()
            raise ConfigEntryNotReady(f"Session manager initialization failed: {err}") from err

        # Store data in hass
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "session_manager": session_manager,
            "title": entry.title,
            "options": entry.options.copy(),
            "entities": {platform: {} for platform in PLATFORMS},
        }

        # Set up each platform individually with error handling
        setup_tasks = []
        for platform in PLATFORMS:
            try:
                setup_tasks.append(
                    hass.config_entries.async_forward_entry_setup(entry, platform)
                )
            except Exception as err:
                _LOGGER.error("Error setting up platform %s: %s", platform, str(err))
                raise

        if setup_tasks:
            await asyncio.gather(*setup_tasks)

        # Register update listener
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))

        return True

    except Exception as err:
        _LOGGER.error("Error setting up Eveus integration: %s", str(err))
        
        # Clean up if setup failed
        if entry.entry_id in hass.data.get(DOMAIN, {}):
            session_manager = hass.data[DOMAIN][entry.entry_id].get("session_manager")
            if session_manager:
                await session_manager.close()
            hass.data[DOMAIN].pop(entry.entry_id)
            
        raise ConfigEntryNotReady(str(err)) from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry with proper cleanup."""
    if entry.entry_id not in hass.data.get(DOMAIN, {}):
        return True

    try:
        # Unload platforms individually
        unload_tasks = []
        for platform in PLATFORMS:
            try:
                unload_tasks.append(
                    hass.config_entries.async_forward_entry_unload(entry, platform)
                )
            except Exception as err:
                _LOGGER.error(
                    "Error unloading platform %s: %s",
                    platform,
                    str(err)
                )

        # Wait for all unload tasks
        if unload_tasks:
            results = await asyncio.gather(*unload_tasks, return_exceptions=True)
            unload_ok = all(
                result is True for result in results
                if not isinstance(result, Exception)
            )
        else:
            unload_ok = True

        # Clean up session manager
        if unload_ok:
            session_manager = hass.data[DOMAIN][entry.entry_id]["session_manager"]
            try:
                await session_manager.close()
            except Exception as err:
                _LOGGER.error("Error closing session manager: %s", str(err))

            # Remove entry data
            hass.data[DOMAIN].pop(entry.entry_id)

        return unload_ok

    except Exception as err:
        _LOGGER.error("Error unloading entry: %s", str(err))
        return False

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    try:
        await async_setup_entry(hass, entry)
    except Exception as err:
        _LOGGER.error("Error reloading entry: %s", str(err))
        raise ConfigEntryNotReady(f"Reload failed: {err}") from err
