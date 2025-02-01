"""Support for Eveus sensors."""
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .sensors import (
    EveusVoltageSensor,
    EveusCurrentSensor,
    EveusPowerSensor,
    EveusStateSensor,
    EveusSubstateSensor,
    EveusBoxTemperatureSensor,
    EveusPlugTemperatureSensor,
    EveusSystemTimeSensor,
    EveusSessionTimeSensor,
    EveusCounterAEnergySensor,
    EveusCounterBEnergySensor,
    EveusCounterACostSensor,
    EveusCounterBCostSensor,
    EVSocKwhSensor,
    EVSocPercentSensor,
    TimeToTargetSocSensor,
)

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
