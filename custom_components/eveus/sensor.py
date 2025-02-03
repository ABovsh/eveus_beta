"""Support for Eveus sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .basic_sensors import (
    EveusSensorBase,
    EveusVoltageSensor,
    EveusCurrentSensor,
    EveusPowerSensor,
    EveusCurrentSetSensor,
    EveusCurrentDesignedSensor,
    EveusSessionTimeSensor,
    EveusFormattedSessionTimeSensor,
    EveusSessionEnergySensor,
    EveusTotalEnergySensor,
)
from .ev_sensors import (
    EVSocKwhSensor,
    EVSocPercentSensor,
    TimeToTargetSocSensor,
)
from .diag_sensors import (
    EveusConnectionErrorsSensor,
    EveusStateSensor,
    EveusSubstateSensor,
    EveusEnabledSensor,
    EveusGroundSensor,
    EveusGroundControlSensor,
    EveusBoxTemperatureSensor,
    EveusPlugTemperatureSensor,
    EveusBatteryVoltageSensor,
    EveusSystemTimeSensor,
)
from .adaptive_sensors import (
    EveusAdaptiveVoltageSensor,
    EveusAdaptiveCurrentSensor,
    EveusAdaptiveStatusSensor,
)
from .counter_sensors import (
    EveusCounterAEnergySensor,
    EveusCounterACostSensor,
    EveusCounterBEnergySensor,
    EveusCounterBCostSensor,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eveus sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    updater = data["updater"]

    sensors = [
        # Basic measurement sensors
        EveusVoltageSensor(updater),
        EveusCurrentSensor(updater),
        EveusPowerSensor(updater),
        EveusCurrentSetSensor(updater),
        EveusCurrentDesignedSensor(updater),
        EveusSessionTimeSensor(updater),
        EveusFormattedSessionTimeSensor(updater),
        EveusSessionEnergySensor(updater),
        EveusTotalEnergySensor(updater),
        
        # Adaptive mode sensors
        EveusAdaptiveVoltageSensor(updater),
        EveusAdaptiveCurrentSensor(updater),
        EveusAdaptiveStatusSensor(updater),
        
        # Counter sensors
        EveusCounterAEnergySensor(updater),
        EveusCounterACostSensor(updater),
        EveusCounterBEnergySensor(updater),
        EveusCounterBCostSensor(updater),
        
        # Diagnostic sensors
        EveusConnectionErrorsSensor(updater),
        EveusStateSensor(updater),
        EveusSubstateSensor(updater),
        EveusEnabledSensor(updater),
        EveusGroundSensor(updater),
        EveusGroundControlSensor(updater),
        EveusBoxTemperatureSensor(updater),
        EveusPlugTemperatureSensor(updater),
        EveusBatteryVoltageSensor(updater),
        EveusSystemTimeSensor(updater),
        
        # EV-specific sensors
        EVSocKwhSensor(updater),
        EVSocPercentSensor(updater),
        TimeToTargetSocSensor(updater),
    ]

    # Initialize entities dict if needed
    if "entities" not in data:
        data["entities"] = {}

    data["entities"]["sensor"] = {
        sensor.unique_id: sensor for sensor in sensors
    }

    async_add_entities(sensors)
