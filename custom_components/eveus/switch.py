"""Support for Eveus switches."""
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .switches import (
    EveusChargingSwitch,
    EveusOneChargeSwitch,
    EveusResetCounterSwitch,
)

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
