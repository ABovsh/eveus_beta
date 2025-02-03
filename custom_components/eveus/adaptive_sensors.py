"""Support for Eveus adaptive mode sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
)

from .common import EveusSensorBase

_LOGGER = logging.getLogger(__name__)

class EveusAdaptiveVoltageSensor(EveusSensorBase):
    """Adaptive mode voltage sensor."""

    ENTITY_NAME = "Adaptive Mode Voltage"
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:sine-wave"
    _attr_suggested_display_precision = 0

    @property
    def native_value(self) -> float | None:
        """Return adaptive mode voltage."""
        try:
            value = self._updater.data.get("aiVoltage")
            if value in (None, "unknown"):
                return None
            return float(value)
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error getting adaptive mode voltage: %s", err)
            return None

class EveusAdaptiveCurrentSensor(EveusSensorBase):
    """Adaptive mode current sensor."""

    ENTITY_NAME = "Adaptive Mode Current"
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:sine-wave"
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return adaptive mode current."""
        try:
            value = self._updater.data.get("aiCurrent")
            if value in (None, "unknown"):
                return None
            return float(value)
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error getting adaptive mode current: %s", err)
            return None

class EveusAdaptiveStatusSensor(EveusSensorBase):
    """Adaptive mode status sensor."""

    ENTITY_NAME = "Adaptive Mode Status"
    _attr_icon = "mdi:sine-wave"

    @property
    def native_value(self) -> str | None:
        """Return adaptive mode status."""
        try:
            value = self._updater.data.get("aiStatus")
            if value in (None, "unknown"):
                return None
            return str(value)
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error getting adaptive mode status: %s", err)
            return None
