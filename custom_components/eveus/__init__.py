"""The Eveus integration."""
from __future__ import annotations

import asyncio
import logging
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
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_platform

from .const import (
    DOMAIN,
    UPDATE_INTERVAL_IDLE,
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

# Define required helper entities and their valid ranges
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

async def async_setup_platform(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up platform."""
    platform = entry.platform
    _LOGGER.debug(f"Setting up {platform} platform")

    if platform == Platform.SENSOR:
        from .sensor import async_setup_entry as setup_sensor
        await setup_sensor(hass, entry, async_add_entities)
    elif platform == Platform.SWITCH:
        from .switch import async_setup_entry as setup_switch
        await setup_switch(hass, entry, async_add_entities)
    elif platform == Platform.NUMBER:
        from .number import async_setup_entry as setup_number
        await setup_number(hass, entry, async_add_entities)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eveus from a config entry."""
    try:
        if DOMAIN not in hass.data:
            hass.data[DOMAIN] = {}
            
        if entry.entry_id in hass.data[DOMAIN]:
            return True

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

        hass.data[DOMAIN][entry.entry_id] = {
            "session_manager": session_manager,
            "title": entry.title,
            "options": entry.options.copy(),
            "entities": {platform: {} for platform in PLATFORMS},
        }

        # Use async_forward_entry_setups instead of async_forward_entry_setup
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        unload_ok = True
        
        # Unload platforms
        for platform in PLATFORMS:
            try:
                unload_ok = unload_ok and await hass.config_entries.async_forward_entry_unload(
                    entry, platform
                )
            except Exception as err:
                _LOGGER.error(f"Error unloading {platform}: {err}")
                unload_ok = False

        # Clean up if unload was successful
        if unload_ok and entry.entry_id in hass.data[DOMAIN]:
            session_manager = hass.data[DOMAIN][entry.entry_id]["session_manager"]
            await session_manager.close()
            hass.data[DOMAIN].pop(entry.entry_id)

        return unload_ok

    except Exception as err:
        _LOGGER.error("Error unloading entry: %s", str(err))
        return False

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle an options update."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
