"""Platform for Eveus sensor integration."""
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .sensors.energy import (
    EveusVoltageSensor,
    EveusCurrentSensor,
    EveusPowerSensor,
    EveusCounterAEnergySensor,
    EveusCounterBEnergySensor,
    EveusCounterACostSensor,
    EveusCounterBCostSensor,
)
from .sensors.diagnostic import (
    EveusStateSensor,
    EveusSubstateSensor,
    EveusBoxTemperatureSensor,
    EveusPlugTemperatureSensor,
    EveusSystemTimeSensor,
    EveusSessionTimeSensor,
)
from .sensors.ev import (
    EVSocKwhSensor,
    EVSocPercentSensor,
    TimeToTargetSocSensor,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus sensor based on a config entry."""
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    
    entities = [
        EveusVoltageSensor(client),
        EveusCurrentSensor(client),
        EveusPowerSensor(client),
        EveusStateSensor(client),
        EveusSubstateSensor(client),
        EveusBoxTemperatureSensor(client),
        EveusPlugTemperatureSensor(client),
        EveusSystemTimeSensor(client),
        EveusSessionTimeSensor(client),
        EveusCounterAEnergySensor(client),
        EveusCounterBEnergySensor(client),
        EveusCounterACostSensor(client),
        EveusCounterBCostSensor(client),
        EVSocKwhSensor(client),
        EVSocPercentSensor(client),
        TimeToTargetSocSensor(client),
    ]
    
    async_add_entities(entities)
