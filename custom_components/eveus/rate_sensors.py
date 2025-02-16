"""Support for Eveus rate sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)

from .common import EveusSensorBase
from .const import RATE_STATES
from .utils import get_safe_value

_LOGGER = logging.getLogger(__name__)

class EveusRateSensorBase(EveusSensorBase):
    """Base class for rate sensors."""
    
    _attr_native_unit_of_measurement = "₴/kWh"
    _attr_icon = "mdi:currency-uah"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, updater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_has_entity_name = True

class EveusRateTimeRangeBase(EveusSensorBase):
    """Base class for rate time range sensors."""
    
    _attr_icon = "mdi:clock-outline"

    def _format_time(self, minutes: int) -> str:
        """Convert minutes since midnight to HH:mm format."""
        try:
            hours = minutes // 60
            mins = minutes % 60
            return f"{hours:02d}:{mins:02d}"
        except Exception as err:
            _LOGGER.error("Error formatting time: %s", err)
            return "00:00"

class EveusPrimaryRateCostSensor(EveusRateSensorBase):
    """Primary rate cost sensor."""

    ENTITY_NAME = "Primary Rate Cost"

    @property
    def native_value(self) -> float | None:
        """Return the primary rate cost."""
        try:
            value = get_safe_value(self._updater.data, "tarif", float)
            if value is None:
                return None
            return round(value / 100, 2)
        except Exception as err:
            _LOGGER.error("Error getting primary rate cost: %s", err)
            return None

class EveusActiveRateCostSensor(EveusRateSensorBase):
    """Active rate cost sensor."""

    ENTITY_NAME = "Active Rate Cost"

    @property
    def native_value(self) -> float | None:
        """Return the active rate cost."""
        try:
            active_rate = get_safe_value(self._updater.data, "activeTarif", int)
            if active_rate is None:
                return None

            if active_rate == 0:
                value = get_safe_value(self._updater.data, "tarif", float)
            elif active_rate == 1:
                value = get_safe_value(self._updater.data, "tarifAValue", float)
            elif active_rate == 2:
                value = get_safe_value(self._updater.data, "tarifBValue", float)
            else:
                return None

            return round(value / 100, 2) if value is not None else None
        except Exception as err:
            _LOGGER.error("Error getting active rate cost: %s", err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return rate name."""
        try:
            active_rate = get_safe_value(self._updater.data, "activeTarif", int)
            if active_rate is not None:
                return {"rate_name": RATE_STATES.get(active_rate, "Unknown")}
        except Exception:
            pass
        return {}

class EveusRate2CostSensor(EveusRateSensorBase):
    """Rate 2 cost sensor."""

    ENTITY_NAME = "Rate 2 Cost"

    @property
    def native_value(self) -> float | None:
        """Return rate 2 cost."""
        try:
            value = get_safe_value(self._updater.data, "tarifAValue", float)
            if value is None:
                return None
            return round(value / 100, 2)
        except Exception as err:
            _LOGGER.error("Error getting rate 2 cost: %s", err)
            return None

class EveusRate3CostSensor(EveusRateSensorBase):
    """Rate 3 cost sensor."""

    ENTITY_NAME = "Rate 3 Cost"

    @property
    def native_value(self) -> float | None:
        """Return rate 3 cost."""
        try:
            value = get_safe_value(self._updater.data, "tarifBValue", float)
            if value is None:
                return None
            return round(value / 100, 2)
        except Exception as err:
            _LOGGER.error("Error getting rate 3 cost: %s", err)
            return None

class EveusRate2StatusSensor(EveusSensorBase):
    """Rate 2 status sensor."""

    ENTITY_NAME = "Rate 2 Status"
    _attr_icon = "mdi:clock-check"

    @property
    def native_value(self) -> str | None:
        """Return rate 2 status."""
        try:
            enabled = get_safe_value(self._updater.data, "tarifAEnable", int)
            if enabled is None:
                return None
            return "Enabled" if enabled == 1 else "Disabled"
        except Exception as err:
            _LOGGER.error("Error getting rate 2 status: %s", err)
            return None

class EveusRate3StatusSensor(EveusSensorBase):
    """Rate 3 status sensor."""

    ENTITY_NAME = "Rate 3 Status"
    _attr_icon = "mdi:clock-check"

    @property
    def native_value(self) -> str | None:
        """Return rate 3 status."""
        try:
            enabled = get_safe_value(self._updater.data, "tarifBEnable", int)
            if enabled is None:
                return None
            return "Enabled" if enabled == 1 else "Disabled"
        except Exception as err:
            _LOGGER.error("Error getting rate 3 status: %s", err)
            return None

class EveusPrimaryRateTimeRangeSensor(EveusRateTimeRangeBase):
    """Primary rate time range sensor."""

    ENTITY_NAME = "Primary Rate Timerange"

    @property
    def native_value(self) -> str | None:
        """Return primary rate time range."""
        try:
            rate2_enabled = get_safe_value(self._updater.data, "tarifAEnable", int)
            rate3_enabled = get_safe_value(self._updater.data, "tarifBEnable", int)

            if rate2_enabled:
                rate2_start = get_safe_value(self._updater.data, "tarifAStart", int)
                rate2_stop = get_safe_value(self._updater.data, "tarifAStop", int)
                
                # If rate 2 is enabled, primary rate runs from rate2_stop to rate2_start
                return f"{self._format_time(rate2_stop)} - {self._format_time(rate2_start)}"
            
            if rate3_enabled:
                rate3_start = get_safe_value(self._updater.data, "tarifBStart", int)
                rate3_stop = get_safe_value(self._updater.data, "tarifBStop", int)
                
                # If only rate 3 is enabled, primary rate runs from rate3_stop to rate3_start
                return f"{self._format_time(rate3_stop)} - {self._format_time(rate3_start)}"
            
            # If no other rates enabled, primary rate runs 24/7
            return "00:00 - 23:59"
            
        except Exception as err:
            _LOGGER.error("Error getting primary rate timerange: %s", err)
            return None

class EveusRate2TimeRangeSensor(EveusRateTimeRangeBase):
    """Rate 2 time range sensor."""

    ENTITY_NAME = "Rate 2 Timerange"

    @property
    def native_value(self) -> str | None:
        """Return rate 2 time range."""
        try:
            rate2_enabled = get_safe_value(self._updater.data, "tarifAEnable", int)
            if not rate2_enabled:
                return "Disabled"

            start = get_safe_value(self._updater.data, "tarifAStart", int)
            stop = get_safe_value(self._updater.data, "tarifAStop", int)
            
            return f"{self._format_time(start)} - {self._format_time(stop)}"
            
        except Exception as err:
            _LOGGER.error("Error getting rate 2 timerange: %s", err)
            return None

class EveusRate3TimeRangeSensor(EveusRateTimeRangeBase):
    """Rate 3 time range sensor."""

    ENTITY_NAME = "Rate 3 Timerange"

    @property
    def native_value(self) -> str | None:
        """Return rate 3 time range."""
        try:
            rate3_enabled = get_safe_value(self._updater.data, "tarifBEnable", int)
            if not rate3_enabled:
                return "Disabled"

            start = get_safe_value(self._updater.data, "tarifBStart", int)
            stop = get_safe_value(self._updater.data, "tarifBStop", int)
            
            return f"{self._format_time(start)} - {self._format_time(stop)}"
            
        except Exception as err:
            _LOGGER.error("Error getting rate 3 timerange: %s", err)
            return None
