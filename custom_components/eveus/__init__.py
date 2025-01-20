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

        # Initialize session manager
        session_manager = SessionManager(
            hass=hass,
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            entry_id=entry.entry_id,
        )

        await session_manager.initialize()

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

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry reload."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
