"""Support for Eveus switch platform."""
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entities import (
    EveusChargingSwitch,
    EveusOneChargeSwitch,
    EveusResetCounterSwitch,
)
from ..const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eveus switch entities."""
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    
    switches = [
        EveusChargingSwitch(client),
        EveusOneChargeSwitch(client),
        EveusResetCounterSwitch(client),
    ]
    
    async_add_entities(switches)
