"""The Eveus integration."""
from __future__ import annotations

import logging
import asyncio
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
from homeassistant.helpers.entity_registry import async_get as get_entity_registry
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    HELPER_EV_BATTERY_CAPACITY,
    HELPER_EV_INITIAL_SOC,
    HELPER_EV_SOC_CORRECTION,
    HELPER_EV_TARGET_SOC,
)
from .session_manager import SessionManager

from homeassistant.helpers.entity_registry import (
    async_get as get_entity_registry,
    async_entries_for_config_entry,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Eveus component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def validate_helper_entities(hass: HomeAssistant) -> tuple[bool, list[str]]:
    """Validate required helper entities exist and are configured."""
    required_helpers = [
        HELPER_EV_BATTERY_CAPACITY,
        HELPER_EV_INITIAL_SOC,
        HELPER_EV_SOC_CORRECTION,
        HELPER_EV_TARGET_SOC
    ]
    
    missing_helpers = []
    for helper in required_helpers:
        if not hass.states.get(helper):
            missing_helpers.append(helper)
            
    return len(missing_helpers) == 0, missing_helpers

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eveus from a config entry."""
    try:
        # Validate helper entities
        valid_helpers, missing = await validate_helper_entities(hass)
        if not valid_helpers:
            raise ConfigEntryNotReady(
                f"Missing required helper entities: {', '.join(missing)}"
            )

        # Initialize session manager in the executor
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

        # Initialize session manager and test connection
        try:
            await session_manager.initialize()
            
            # Update entry data
            data_update = {}
            if session_manager.firmware_version:
                data_update["firmware_version"] = session_manager.firmware_version
            if session_manager.station_id:
                data_update["station_id"] = session_manager.station_id
            if session_manager.capabilities:
                data_update["min_current"] = session_manager.capabilities["min_current"]
                data_update["max_current"] = session_manager.capabilities["max_current"]
                
            if data_update:
                hass.config_entries.async_update_entry(
                    entry, 
                    data={**entry.data, **data_update}
                )

            # Update device registry
            device_registry = dr.async_get(hass)
            device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, entry.data[CONF_HOST])},
                manufacturer="Eveus",
                name=f"Current range: {session_manager.capabilities['min_current']}-{session_manager.capabilities['max_current']}A",
                model="Eveus",
                sw_version=session_manager.firmware_version,
                configuration_url=f"http://{entry.data[CONF_HOST]}",
                serial_number=session_manager.station_id
            )
                
        except Exception as err:
            await session_manager.close()
            _LOGGER.error("Failed to initialize session manager: %s", str(err))
            raise ConfigEntryNotReady from err

        # Store session manager and initialize data structure
        hass.data[DOMAIN][entry.entry_id] = {
            "session_manager": session_manager,
            "title": entry.title,
            "options": entry.options.copy(),
            "entities": {
                "sensor": {},
                "switch": {},
                "number": {},
            },
        }

        # Forward to platform setup
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Register update listener
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))

        return True

    except Exception as err:
        _LOGGER.error("Error setting up Eveus integration: %s", str(err))
        raise ConfigEntryNotReady from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        # Unload platforms
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

        if unload_ok:
            # Clean up entities
            entity_registry = get_entity_registry(hass)
            entries = async_entries_for_config_entry(entity_registry, entry.entry_id)
            for entity_entry in entries:
                if entity_entry.entity_id not in [
                    entity.entity_id 
                    for platform_entities in hass.data[DOMAIN][entry.entry_id]["entities"].values()
                    for entity in platform_entities.values()
                ]:
                    entity_registry.async_remove(entity_entry.entity_id)

            # Close session manager
            session_manager = hass.data[DOMAIN][entry.entry_id]["session_manager"]
            await session_manager.close()

            # Remove entry data
            hass.data[DOMAIN].pop(entry.entry_id)

        return unload_ok
        
    except Exception as err:
        _LOGGER.error("Error unloading entry: %s", str(err))
        return False

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry reload."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
