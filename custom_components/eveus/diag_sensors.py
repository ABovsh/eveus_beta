"""Support for Eveus diagnostic sensors."""
from __future__ import annotations

import logging
from typing import Any
import time
from datetime import datetime, timedelta
from collections import Counter
import pytz

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
from .utils import get_safe_value, is_dst

_LOGGER = logging.getLogger(__name__)

class EveusDiagnosticSensor(BaseEveusEntity, SensorEntity):
    """Base diagnostic sensor."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information"

class EveusConnectionQualitySensor(EveusDiagnosticSensor):
    """Connection quality metrics sensor with enhanced monitoring."""

    ENTITY_NAME = "Connection Quality"
    _attr_icon = "mdi:connection"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    MAX_ERROR_HISTORY = 50  # Limit error history storage

    def __init__(self, updater) -> None:
        """Initialize with metric caching."""
        super().__init__(updater)
        self._cached_metrics = None
        self._last_update = 0
        self._update_interval = 30  # Update metrics every 30 seconds

    @property
    def native_value(self) -> float:
        """Return bounded and validated connection quality percentage."""
        try:
            success_rate = self._updater._network.connection_quality['success_rate']
            # Ensure value is within valid range
            return round(max(0, min(100, success_rate)))
        except Exception as err:
            _LOGGER.error("Error calculating connection quality: %s", err)
            return 0

    def _get_error_summary(self) -> dict:
        """Get summarized error information."""
        error_types = self._updater._network._quality_metrics['error_types']
        total_errors = sum(error_types.values())
        
        return {
            "total_errors": total_errors,
            "error_distribution": {
                error_type: {
                    "count": count,
                    "percentage": round((count / total_errors * 100), 1) if total_errors else 0
                }
                for error_type, count in error_types.most_common(5)  # Show top 5 errors
            } if total_errors else {}
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return enhanced metrics with caching and validation."""
        current_time = time.time()
        
        # Use cached metrics if within update interval
        if self._cached_metrics and (current_time - self._last_update) < self._update_interval:
            return self._cached_metrics

        try:
            metrics = self._updater._network.connection_quality
            
            # Validate and bound metrics
            latency = max(0, metrics['latency_avg'])
            requests = max(0, metrics['requests_per_minute'])
            
            # Get error summary
            error_summary = self._get_error_summary()
            
            # Format last errors with precise timestamps
            last_errors = [
                {
                    "type": err["type"],
                    "time": datetime.fromtimestamp(err["timestamp"]).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                    "age": f"{round(current_time - err['timestamp'], 1)}s ago"
                }
                for err in list(self._updater._network._quality_metrics['last_errors'])[-self.MAX_ERROR_HISTORY:]
            ]

            # Create new metrics dictionary
            self._cached_metrics = {
                "latency_avg": f"{latency:.2f}s",
                "recent_errors": metrics['recent_errors'],
                "requests_per_minute": requests,
                "error_summary": error_summary,
                "last_errors": last_errors,
                "update_age": "0s"
            }
            self._last_update = current_time
            
            return self._cached_metrics

        except Exception as err:
            _LOGGER.error("Error processing connection metrics: %s", err)
            # Return last known good metrics if available
            if self._cached_metrics:
                self._cached_metrics["update_age"] = f"{round(current_time - self._last_update, 1)}s"
                return self._cached_metrics
            return {
                "error": "Failed to retrieve metrics",
                "last_update_attempt": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

class EveusStateSensor(EveusDiagnosticSensor):
    """Charging state sensor."""
    
    ENTITY_NAME = "State"
    _attr_icon = "mdi:state-machine"

    @property
    def native_value(self) -> str:
        """Return charging state."""
        state_value = get_safe_value(self._updater.data, "state", int)
        if state_value is not None:
            return CHARGING_STATES.get(state_value, "Unknown")
        return None

class EveusSubstateSensor(EveusDiagnosticSensor):
    """Charger substate sensor."""
    
    ENTITY_NAME = "Substate"
    _attr_icon = "mdi:information-variant"

    @property
    def native_value(self) -> str:
        """Return substate with context."""
        state = get_safe_value(self._updater.data, "state", int)
        substate = get_safe_value(self._updater.data, "subState", int)
        
        if None in (state, substate):
            return None
            
        if state == 7:  # Error state
            return ERROR_STATES.get(substate, "Unknown Error")
        return NORMAL_SUBSTATES.get(substate, "Unknown State")

class EveusGroundSensor(EveusDiagnosticSensor):
    """Ground connection sensor."""
    
    ENTITY_NAME = "Ground"
    _attr_icon = "mdi:electric-switch"

    @property
    def native_value(self) -> str:
        """Return ground status."""
        value = get_safe_value(self._updater.data, "ground", int)
        if value is not None:
            return "Connected" if value == 1 else "Not Connected"
        return None

class EveusTemperatureSensorBase(EveusDiagnosticSensor):
    """Base temperature sensor."""
    
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

class EveusBoxTemperatureSensor(EveusTemperatureSensorBase):
    """Box temperature sensor."""
    
    ENTITY_NAME = "Box Temperature"
    DATA_KEY = "temperature1"
    _attr_icon = "mdi:thermometer"

    @property
    def native_value(self) -> float | None:
        """Return box temperature."""
        return get_safe_value(self._updater.data, self.DATA_KEY)

class EveusPlugTemperatureSensor(EveusTemperatureSensorBase):
    """Plug temperature sensor."""
    
    ENTITY_NAME = "Plug Temperature"
    DATA_KEY = "temperature2"
    _attr_icon = "mdi:thermometer-high"

    @property
    def native_value(self) -> float | None:
        """Return plug temperature."""
        return get_safe_value(self._updater.data, self.DATA_KEY)

class EveusBatteryVoltageSensor(EveusDiagnosticSensor):
    """Battery voltage sensor."""
    
    ENTITY_NAME = "Battery Voltage"
    DATA_KEY = "vBat"
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = "V"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery"
    _attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return battery voltage."""
        return get_safe_value(self._updater.data, self.DATA_KEY)

class EveusSystemTimeSensor(EveusDiagnosticSensor):
    """System time sensor."""
    
    ENTITY_NAME = "System Time"
    DATA_KEY = "systemTime"
    _attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> str:
        """Return timezone-corrected system time."""
        try:
            timestamp = get_safe_value(self._updater.data, self.DATA_KEY, int)
            if timestamp is None:
                return None
                
            # Get HA timezone
            ha_timezone = self.hass.config.time_zone
            if not ha_timezone:
                _LOGGER.warning("No timezone set in Home Assistant configuration")
                return None

            # Convert timestamp to datetime in UTC
            dt_utc = datetime.fromtimestamp(timestamp, tz=pytz.UTC)
            
            # Get local timezone
            local_tz = pytz.timezone(ha_timezone)
            
            # Check if we're in DST
            offset = 7200  # Base offset (2 hours)
            if is_dst(ha_timezone, dt_utc):
                offset += 3600  # Add 1 hour during DST
            
            # Apply correction
            corrected_timestamp = timestamp - offset
            dt_corrected = datetime.fromtimestamp(corrected_timestamp, tz=pytz.UTC)
            dt_local = dt_corrected.astimezone(local_tz)
            
            return dt_local.strftime("%H:%M")
                
        except Exception as err:
            _LOGGER.error("Error getting system time: %s", err)
            return None
