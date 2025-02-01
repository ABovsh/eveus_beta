"""Platform for Eveus sensor integration."""
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .sensors.energy import (
    EveusVoltageSensor,
    EveusCurrentSensor,
    EveusPowerSensor,
    EveusSessionEnergySensor,
    EveusTotalEnergySensor,
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
        EveusSessionEnergySensor(client),
        EveusTotalEnergySensor(client),
        EveusCounterAEnergySensor(client),
        EveusCounterBEnergySensor(client),
        EveusCounterACostSensor(client),
        EveusCounterBCostSensor(client),
        EVSocKwhSensor(client),
        EVSocPercentSensor(client),
        TimeToTargetSocSensor(client),
    ]
    
    async_add_entities(entities)
