"""Support for Eveus number platform."""
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entities import EveusCurrentNumber
from ..const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eveus number entities."""
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    async_add_entities([EveusCurrentNumber(client)])
