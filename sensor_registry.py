"""Sensor registry for Eveus integration."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Type, Union
from datetime import datetime
import time

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import EntityCategory
import pytz

from .common import EveusSensorBase
from .const import (
    CHARGING_STATES,
    ERROR_STATES,
    NORMAL_SUBSTATES,
    RATE_STATES,
)
from .utils import (
    get_safe_value,
    is_dst,
    format_duration,
)

_LOGGER = logging.getLogger(__name__)

class SensorDefinition:
    """Sensor definition class for template-based sensor creation."""

    def __init__(
        self,
        entity_name: str,
        value_fn: Callable,
        icon: Optional[str] = None,
        device_class: Optional[str] = None,
        state_class: Optional[str] = None,
        unit: Optional[str] = None,
        precision: Optional[int] = None,
        category: Optional[EntityCategory] = None,
        attributes_fn: Optional[Callable] = None,
        sensor_class: Optional[Type[EveusSensorBase]] = None,
    ):
        """Initialize sensor definition."""
        self.entity_name = entity_name
        self.value_fn = value_fn
        self.icon = icon
        self.device_class = device_class
        self.state_class = state_class
        self.unit = unit
        self.precision = precision
        self.category = category
        self.attributes_fn = attributes_fn
        self.sensor_class = sensor_class or EveusSensorBase

    def create_sensor(self, updater):
        """Create a sensor from this definition."""
        return EveusTemplatedSensor(updater, self)


class EveusTemplatedSensor(EveusSensorBase):
    """Templated sensor based on definitions."""

    def __init__(self, updater, definition: SensorDefinition):
        """Initialize the sensor with a definition."""
        self.ENTITY_NAME = definition.entity_name
        super().__init__(updater)
        
        self._definition = definition
        self._value = None
        
        # Apply definition attributes
        if definition.icon:
            self._attr_icon = definition.icon
        if definition.device_class:
            self._attr_device_class = definition.device_class
        if definition.state_class:
            self._attr_state_class = definition.state_class
        if definition.unit:
            self._attr_native_unit_of_measurement = definition.unit
        if definition.precision is not None:
            self._attr_suggested_display_precision = definition.precision
        if definition.category:
            self._attr_entity_category = definition.category

    @property
    def native_value(self) -> Any:
        """Return the sensor value from definition."""
        try:
            return self._definition.value_fn(self._updater, self.hass)
        except Exception as err:
            _LOGGER.error("Error getting value for %s: %s", self.name, err)
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes if defined."""
        if self._definition.attributes_fn:
            try:
                return self._definition.attributes_fn(self._updater, self.hass)
            except Exception as err:
                _LOGGER.error("Error getting attributes for %s: %s", self.name, err)
        return {}


# Define sensor value functions
def get_voltage(updater, hass) -> float:
    """Get voltage value."""
    value = get_safe_value(updater.data, "voltMeas1")
    return None if value is None else round(value, 0)

def get_current(updater, hass) -> float:
    """Get current value."""
    value = get_safe_value(updater.data, "curMeas1")
    return None if value is None else round(value, 1)

def get_power(updater, hass) -> float:
    """Get power value."""
    value = get_safe_value(updater.data, "powerMeas")
    return None if value is None else round(value, 1)

def get_current_set(updater, hass) -> float:
    """Get current set value."""
    value = get_safe_value(updater.data, "currentSet")
    return None if value is None else round(value, 0)

def get_session_time(updater, hass) -> str:
    """Get formatted session time."""
    seconds = get_safe_value(updater.data, "sessionTime", int)
    return None if seconds is None else format_duration(seconds)

def get_session_time_attrs(updater, hass) -> dict:
    """Get session time attributes."""
    seconds = get_safe_value(updater.data, "sessionTime", int)
    return {"duration_seconds": seconds} if seconds is not None else {}

def get_session_energy(updater, hass) -> float:
    """Get session energy."""
    value = get_safe_value(updater.data, "sessionEnergy")
    return None if value is None else round(value, 2)

def get_total_energy(updater, hass) -> float:
    """Get total energy."""
    value = get_safe_value(updater.data, "totalEnergy")
    return None if value is None else round(value, 2)

def get_counter_a_energy(updater, hass) -> float:
    """Get counter A energy."""
    value = get_safe_value(updater.data, "IEM1")
    return None if value is None else round(value, 2)

def get_counter_a_cost(updater, hass) -> float:
    """Get counter A cost."""
    value = get_safe_value(updater.data, "IEM1_money")
    return None if value is None else round(value, 2)

def get_counter_b_energy(updater, hass) -> float:
    """Get counter B energy."""
    value = get_safe_value(updater.data, "IEM2")
    return None if value is None else round(value, 2)

def get_counter_b_cost(updater, hass) -> float:
    """Get counter B cost."""
    value = get_safe_value(updater.data, "IEM2_money")
    return None if value is None else round(value, 2)

def get_charger_state(updater, hass) -> str:
    """Get charger state."""
    state_value = get_safe_value(updater.data, "state", int)
    if state_value is not None:
        return CHARGING_STATES.get(state_value, "Unknown")
    return None

def get_charger_substate(updater, hass) -> str:
    """Get charger substate."""
    state = get_safe_value(updater.data, "state", int)
    substate = get_safe_value(updater.data, "subState", int)
    
    if None in (state, substate):
        return None
        
    if state == 7:  # Error state
        return ERROR_STATES.get(substate, "Unknown Error")
    return NORMAL_SUBSTATES.get(substate, "Unknown State")

def get_ground_status(updater, hass) -> str:
    """Get ground status."""
    value = get_safe_value(updater.data, "ground", int)
    if value is not None:
        return "Connected" if value == 1 else "Not Connected"
    return None

def get_box_temperature(updater, hass) -> float:
    """Get box temperature."""
    return get_safe_value(updater.data, "temperature1")

def get_plug_temperature(updater, hass) -> float:
    """Get plug temperature."""
    return get_safe_value(updater.data, "temperature2")

def get_battery_voltage(updater, hass) -> float:
    """Get battery voltage."""
    value = get_safe_value(updater.data, "vBat")
    return None if value is None else round(value, 2)

def get_system_time(updater, hass) -> str:
    """Get system time with timezone correction."""
    try:
        timestamp = get_safe_value(updater.data, "systemTime", int)
        if timestamp is None:
            return None
            
        # Get HA timezone
        ha_timezone = hass.config.time_zone
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

def get_primary_rate_cost(updater, hass) -> float:
    """Get primary rate cost."""
    value = get_safe_value(updater.data, "tarif", float)
    return None if value is None else round(value / 100, 2)

def get_active_rate_cost(updater, hass) -> float:
    """Get active rate cost."""
    try:
        active_rate = get_safe_value(updater.data, "activeTarif", int)
        if active_rate is None:
            return None

        if active_rate == 0:
            value = get_safe_value(updater.data, "tarif", float)
        elif active_rate == 1:
            value = get_safe_value(updater.data, "tarifAValue", float)
        elif active_rate == 2:
            value = get_safe_value(updater.data, "tarifBValue", float)
        else:
            return None

        return round(value / 100, 2) if value is not None else None
    except Exception as err:
        _LOGGER.error("Error getting active rate cost: %s", err)
        return None

def get_active_rate_attrs(updater, hass) -> dict:
    """Get active rate attributes."""
    try:
        active_rate = get_safe_value(updater.data, "activeTarif", int)
        if active_rate is not None:
            return {"rate_name": RATE_STATES.get(active_rate, "Unknown")}
    except Exception:
        pass
    return {}

def get_rate2_cost(updater, hass) -> float:
    """Get rate 2 cost."""
    value = get_safe_value(updater.data, "tarifAValue", float)
    return None if value is None else round(value / 100, 2)

def get_rate3_cost(updater, hass) -> float:
    """Get rate 3 cost."""
    value = get_safe_value(updater.data, "tarifBValue", float)
    return None if value is None else round(value / 100, 2)

def get_rate2_status(updater, hass) -> str:
    """Get rate 2 status."""
    enabled = get_safe_value(updater.data, "tarifAEnable", int)
    if enabled is None:
        return None
    return "Enabled" if enabled == 1 else "Disabled"

def get_rate3_status(updater, hass) -> str:
    """Get rate 3 status."""
    enabled = get_safe_value(updater.data, "tarifBEnable", int)
    if enabled is None:
        return None
    return "Enabled" if enabled == 1 else "Disabled"

def get_connection_quality(updater, hass) -> float:
    """Get connection quality metrics as numeric value (not percentage string)."""
    try:
        metrics = updater._network.connection_quality
        return round(max(0, min(100, metrics['success_rate'])))
    except Exception as err:
        _LOGGER.error("Error getting connection quality: %s", err)
        return 0

def get_connection_attrs(updater, hass) -> dict:
    """Get enhanced connection quality attributes with comprehensive diagnostics."""
    try:
        metrics = updater._network.connection_quality
        now = time.time()
        
        # Calculate connection trend
        success_history = list(metrics.get('success_rate_history', []))
        trend = "stable"
        if len(success_history) > 10:
            recent_avg = sum(success_history[-5:]) / min(5, len(success_history[-5:]))
            earlier_avg = sum(success_history[-10:-5]) / min(5, len(success_history[-10:-5]))
            if recent_avg > earlier_avg + 10:
                trend = "improving"
            elif recent_avg < earlier_avg - 10:
                trend = "degrading"
        
        # Calculate hourly success rate
        hourly_success = []
        if len(success_history) > 0:
            # Group by hour chunks (simplification)
            chunk_size = min(12, len(success_history) // 4 + 1)  # Avoid dividing by zero
            for i in range(0, len(success_history), chunk_size):
                chunk = success_history[i:i+chunk_size]
                if chunk:
                    hourly_success.append(round(sum(chunk) / len(chunk), 1))
        
        # Basic attributes
        attrs = {
            "connection_quality": f"{round(max(0, min(100, metrics['success_rate'])))}%",
            "latency_avg": f"{max(0, metrics['latency_avg']):.2f}s",
            "recent_errors": metrics['recent_errors'],
            "requests_per_minute": max(0, metrics['requests_per_minute']),
            "status": "Excellent" if metrics['success_rate'] > 95 else 
                     "Good" if metrics['success_rate'] > 80 else
                     "Fair" if metrics['success_rate'] > 60 else
                     "Poor" if metrics['success_rate'] > 30 else "Critical",
            "trend": trend,
            "health_score": metrics.get('health_score', 100),  # Added health score
            "hourly_success_rate": hourly_success,
        }
        
        # Add network diagnostics
        attrs["diagnostics"] = {
            "last_successful_connection": time.strftime('%Y-%m-%d %H:%M:%S', 
                                        time.localtime(metrics['last_successful_connection'])),
            "consecutive_errors": metrics.get('consecutive_errors', 0),
            "uptime": format_duration(int(now - metrics['last_successful_connection'])),
            "peak_requests_per_minute": metrics.get('requests_per_minute', 0),
        }
        
        # Add error analysis
        attrs["error_analysis"] = {
            "error_classes": metrics.get('error_classes', {}),
            "recovery_recommendation": metrics.get('recovery_recommendation', {
                "action": "none",
                "description": "No recovery action needed",
                "severity": "none"
            }),
        }
        
        # Only store last errors with expanded details
        last_errors = updater._network._quality_metrics.get('last_errors', [])
        if last_errors:
            attrs["recent_errors_detail"] = [
                {
                    "type": err.get("type", "Unknown"),
                    "class": err.get("class", "unknown"),
                    "time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(err.get("timestamp", now))),
                    "age": f"{int(now - err.get('timestamp', now))}s ago",
                    "details": err.get("details", "No details available")
                }
                for err in list(last_errors)
            ]
        
        # Add performance metrics
        if 'latency_avg' in metrics:
            attrs["performance"] = {
                "avg_latency": f"{metrics['latency_avg']:.3f}s",
                "min_latency": f"{min(updater._network._quality_metrics.get('latency', [999])) if updater._network._quality_metrics.get('latency') else 0:.3f}s",
                "max_latency": f"{max(updater._network._quality_metrics.get('latency', [0])) if updater._network._quality_metrics.get('latency') else 0:.3f}s",
            }
        
        # Add device connectivity info based on host
        attrs["device_info"] = {
            "host": updater.host,
            "protocol": "http",
        }
            
        return attrs
        
    except Exception as err:
        _LOGGER.error("Error generating connection attributes: %s", err)
        return {
            "error": f"Failed to generate connection attributes: {str(err)}",
            "status": "Unknown"
        }

# Create sensor definitions registry
SENSOR_DEFINITIONS = [
    # Basic sensors
    SensorDefinition(
        entity_name="Voltage",
        value_fn=get_voltage,
        icon="mdi:flash",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfElectricPotential.VOLT,
        precision=0,
    ),
    SensorDefinition(
        entity_name="Current",
        value_fn=get_current,
        icon="mdi:current-ac",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfElectricCurrent.AMPERE,
        precision=1,
    ),
    SensorDefinition(
        entity_name="Power",
        value_fn=get_power,
        icon="mdi:flash",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfPower.WATT,
        precision=1,
    ),
    SensorDefinition(
        entity_name="Current Set",
        value_fn=get_current_set,
        icon="mdi:current-ac",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfElectricCurrent.AMPERE,
        precision=0,
    ),
    SensorDefinition(
        entity_name="Session Time",
        value_fn=get_session_time,
        icon="mdi:timer",
        attributes_fn=get_session_time_attrs,
    ),
    SensorDefinition(
        entity_name="Session Energy",
        value_fn=get_session_energy,
        icon="mdi:transmission-tower-export",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        precision=2,
    ),
    SensorDefinition(
        entity_name="Total Energy",
        value_fn=get_total_energy,
        icon="mdi:transmission-tower",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        precision=2,
    ),
    
    # Counter sensors
    SensorDefinition(
        entity_name="Counter A Energy",
        value_fn=get_counter_a_energy,
        icon="mdi:counter",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        precision=2,
    ),
    SensorDefinition(
        entity_name="Counter A Cost",
        value_fn=get_counter_a_cost,
        icon="mdi:currency-uah",
        state_class=SensorStateClass.TOTAL_INCREASING,
        unit="₴",
        precision=2,
    ),
    SensorDefinition(
        entity_name="Counter B Energy",
        value_fn=get_counter_b_energy,
        icon="mdi:counter",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        precision=2,
    ),
    SensorDefinition(
        entity_name="Counter B Cost",
        value_fn=get_counter_b_cost,
        icon="mdi:currency-uah",
        state_class=SensorStateClass.TOTAL_INCREASING,
        unit="₴",
        precision=2,
    ),
    
    # Diagnostic sensors
    SensorDefinition(
        entity_name="State",
        value_fn=get_charger_state,
        icon="mdi:state-machine",
        category=EntityCategory.DIAGNOSTIC,
    ),
    SensorDefinition(
        entity_name="Substate",
        value_fn=get_charger_substate,
        icon="mdi:information-variant",
        category=EntityCategory.DIAGNOSTIC,
    ),
    SensorDefinition(
        entity_name="Ground",
        value_fn=get_ground_status,
        icon="mdi:electric-switch",
        category=EntityCategory.DIAGNOSTIC,
    ),
    SensorDefinition(
        entity_name="Box Temperature",
        value_fn=get_box_temperature,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfTemperature.CELSIUS,
        precision=0,
        category=EntityCategory.DIAGNOSTIC,
    ),
    SensorDefinition(
        entity_name="Plug Temperature",
        value_fn=get_plug_temperature,
        icon="mdi:thermometer-high",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfTemperature.CELSIUS,
        precision=0,
        category=EntityCategory.DIAGNOSTIC,
    ),
    SensorDefinition(
        entity_name="Battery Voltage",
        value_fn=get_battery_voltage,
        icon="mdi:battery",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        unit="V",
        precision=2,
        category=EntityCategory.DIAGNOSTIC,
    ),
    SensorDefinition(
        entity_name="System Time",
        value_fn=get_system_time,
        icon="mdi:clock-outline",
        category=EntityCategory.DIAGNOSTIC,
    ),
    SensorDefinition(
        entity_name="Connection Quality",
        value_fn=get_connection_quality,
        icon="mdi:connection",
        state_class=SensorStateClass.MEASUREMENT,
        unit="%",  # Add percentage unit
        precision=0,
        category=EntityCategory.DIAGNOSTIC,
        attributes_fn=get_connection_attrs,
    ),
    
    # Rate sensors
    SensorDefinition(
        entity_name="Primary Rate Cost",
        value_fn=get_primary_rate_cost,
        icon="mdi:currency-uah",
        state_class=SensorStateClass.MEASUREMENT,
        unit="₴/kWh",
        precision=2,
    ),
    SensorDefinition(
        entity_name="Active Rate Cost",
        value_fn=get_active_rate_cost,
        icon="mdi:currency-uah",
        state_class=SensorStateClass.MEASUREMENT,
        unit="₴/kWh",
        precision=2,
        attributes_fn=get_active_rate_attrs,
    ),
    SensorDefinition(
        entity_name="Rate 2 Cost",
        value_fn=get_rate2_cost,
        icon="mdi:currency-uah",
        state_class=SensorStateClass.MEASUREMENT,
        unit="₴/kWh",
        precision=2,
    ),
    SensorDefinition(
        entity_name="Rate 3 Cost",
        value_fn=get_rate3_cost,
        icon="mdi:currency-uah",
        state_class=SensorStateClass.MEASUREMENT,
        unit="₴/kWh",
        precision=2,
    ),
    SensorDefinition(
        entity_name="Rate 2 Status",
        value_fn=get_rate2_status,
        icon="mdi:clock-check",
    ),
    SensorDefinition(
        entity_name="Rate 3 Status",
        value_fn=get_rate3_status,
        icon="mdi:clock-check",
    ),
]

def get_sensor_definitions() -> List[SensorDefinition]:
    """Get all sensor definitions."""
    return SENSOR_DEFINITIONS
