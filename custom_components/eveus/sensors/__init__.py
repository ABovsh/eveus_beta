"""Support for Eveus sensor platform."""
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .energy import (
    EveusVoltageSensor,
    EveusCurrentSensor,
    EveusPowerSensor,
    EveusCounterAEnergySensor,
    EveusCounterBEnergySensor,
    EveusCounterACostSensor,
    EveusCounterBCostSensor,
)
from .diagnostic import (
    EveusStateSensor,
    EveusSubstateSensor,
    EveusBoxTemperatureSensor,
    EveusPlugTemperatureSensor,
    EveusSystemTimeSensor,
    EveusSessionTimeSensor,
)
from .ev import (
    EVSocKwhSensor,
    EVSocPercentSensor,
    TimeToTargetSocSensor,
)
from ..const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eveus sensor entities."""
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    
    sensors = [
        EveusVoltageSensor(client),
        EveusCurrentSensor(client),
        EveusPowerSensor(client),
        EveusCurrentSetSensor(client),
        EveusSessionEnergySensor(client),
        EveusTotalEnergySensor(client),
        EveusStateSensor(client),
        EveusSubstateSensor(client),
        EveusSystemTimeSensor(client),
        EveusSessionTimeSensor(client),
        EveusCounterAEnergySensor(client),
        EveusCounterBEnergySensor(client),
        EveusCounterACostSensor(client),
        EveusCounterBCostSensor(client),
        EveusBoxTemperatureSensor(client),
        EveusPlugTemperatureSensor(client),
        EVSocKwhSensor(client),
        EVSocPercentSensor(client),
        TimeToTargetSocSensor(client),
    ]
    
    async_add_entities(sensors)
