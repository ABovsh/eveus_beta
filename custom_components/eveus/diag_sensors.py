"""Support for Eveus diagnostic sensors."""
from __future__ import annotations

import logging
from typing import Any
import time

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory

from .common import BaseEveusEntity
from .const import (
    CHARGING_STATES,
    ERROR_STATES,
    NORMAL_SUBSTATES,
)

_LOGGER = logging.getLogger(__name__)

class EveusDiagnosticSensor(BaseEveusEntity, SensorEntity):
    """Base diagnostic sensor."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information"

class EveusConnectionErrorsSensor(EveusDiagnosticSensor):
    """Failed requests counter sensor."""

    ENTITY_NAME = "Connection Errors"
    _attr_icon = "mdi:connection"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING 

    @property
    def native_value(self) -> int:
        """Return number of failed requests."""
        return self._updater.failed_requests

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional sensor state attributes."""
        return {
            "last_error_time": time.strftime('%Y-%m-%d %H:%M:%S', 
                time.localtime(self._updater.last_error_time)) if self._updater.last_error_time else None,
            "last_error_type": self._updater.last_error_type,
            "consecutive_errors": self._updater.consecutive_errors,
        }

class EveusStateSensor(EveusDiagnosticSensor):
    """Charging state sensor."""
    
    ENTITY_NAME = "State"
    _attr_icon = "mdi:state-machine"

    @property
    def native_value(self) -> str:
        """Return charging state."""
        try:
            state_value = self._updater.data.get("state")
            if state_value is None:
                return None
            return CHARGING_STATES.get(state_value, "Unknown")
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error getting charger state: %s", err)
            return None

class EveusSubstateSensor(EveusDiagnosticSensor):
    """Charger substate sensor."""
    
    ENTITY_NAME = "Substate"
    _attr_icon = "mdi:information-variant"

    @property
    def native_value(self) -> str:
        """Return substate with context."""
        try:
            state = self._updater.data.get("state")
            substate = self._updater.data.get("subState")
            
            if state is None or substate is None:
                return None
                
            if state == 7:  # Error state
                return ERROR_STATES.get(substate, "Unknown Error")
            return NORMAL_SUBSTATES.get(substate, "Unknown State")
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error getting charger substate: %s", err)
            return None

class EveusGroundSensor(EveusDiagnosticSensor):
    """Ground connection sensor."""
    
    ENTITY_NAME = "Ground"
    _attr_icon = "mdi:electric-switch"

    @property
    def native_value(self) -> str:
        """Return ground status."""
        try:
            value = self._updater.data.get("ground")
            if value is None:
                return None
            return "Connected" if value == 1 else "Not Connected"
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error getting ground state: %s", err)
            return None

class EveusBoxTemperatureSensor(EveusDiagnosticSensor):
    """Box temperature sensor."""
    
    ENTITY_NAME = "Box Temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer"
    _attr_suggested_display_precision = 0

    @property
    def native_value(self) -> float | None:
        """Return box temperature."""
        try:
            value = self._updater.data.get("temperature1")
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error getting box temperature: %s", err)
            return None

class EveusPlugTemperatureSensor(EveusDiagnosticSensor):
    """Plug temperature sensor."""
    
    ENTITY_NAME = "Plug Temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer-high"
    _attr_suggested_display_precision = 0

    @property
    def native_value(self) -> float | None:
        """Return plug temperature."""
        try:
            value = self._updater.data.get("temperature2")
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error getting plug temperature: %s", err)
            return None

class EveusBatteryVoltageSensor(EveusDiagnosticSensor):
    """Battery voltage sensor."""
    
    ENTITY_NAME = "Battery Voltage"
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = "V"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery"
    _attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return battery voltage."""
        try:
            value = self._updater.data.get("vBat")
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error getting battery voltage: %s", err)
            return None

class EveusSystemTimeSensor(EveusDiagnosticSensor):
    """System time sensor."""
    
    ENTITY_NAME = "System Time"
    _attr_icon = "mdi:clock-outline"

    def _is_dst(self, timezone_str: str, dt: datetime) -> bool:
        """Check if the given datetime is in DST for the timezone."""
        try:
            tz = pytz.timezone(timezone_str)
            return dt.astimezone(tz).dst() != timedelta(0)
        except Exception:
            return False

    @property
    def native_value(self) -> str:
        """Return timezone-corrected system time."""
        try:
            timestamp = self._updater.data.get("systemTime")
            if timestamp is None:
                return None
                
            # Get HA timezone
            ha_timezone = self.hass.config.time_zone
            if not ha_timezone:
                _LOGGER.warning("No timezone set in Home Assistant configuration")
                return None

            from datetime import datetime, timedelta
            import pytz
            
            # Convert timestamp to datetime in UTC
            base_timestamp = int(timestamp)
            dt_utc = datetime.fromtimestamp(base_timestamp, tz=pytz.UTC)
            
            # Get local timezone
            local_tz = pytz.timezone(ha_timezone)
            
            # Check if we're in DST
            offset = 7200  # Base offset (2 hours)
            if self._is_dst(ha_timezone, dt_utc):
                offset += 3600  # Add 1 hour during DST
            
            # Apply correction
            corrected_timestamp = base_timestamp - offset
            dt_corrected = datetime.fromtimestamp(corrected_timestamp, tz=pytz.UTC)
            dt_local = dt_corrected.astimezone(local_tz)
            
            return dt_local.strftime("%H:%M")
                
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error getting system time: %s", err)
            return None
        except Exception as err:
            _LOGGER.error("Unexpected error getting system time: %s", err)
            return None
