"""Sensor definitions and factory for Eveus integration."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Type, Union
from datetime import datetime
from functools import lru_cache, partial
from dataclasses import dataclass
from enum import Enum

from homeassistant.components.sensor import (
    SensorDeviceClass,
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
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.event import async_track_state_change_event
import pytz

from .common import EveusSensorBase
from .const import (
    get_charging_state,
    get_error_state,
    get_normal_substate,
    RATE_STATES,
)
from .utils import (
    get_safe_value,
    is_dst,
    format_duration,
    calculate_remaining_time,
    validate_required_values,
)

_LOGGER = logging.getLogger(__name__)

class SensorType(Enum):
    """Sensor type enumeration for categorization."""
    MEASUREMENT = "measurement"
    ENERGY = "energy" 
    DIAGNOSTIC = "diagnostic"
    CALCULATED = "calculated"
    STATE = "state"

@dataclass(frozen=True)
class SensorSpec:
    """Immutable sensor specification for efficient sensor creation."""
    key: str
    name: str
    value_fn: Callable
    sensor_type: SensorType
    icon: Optional[str] = None
    device_class: Optional[str] = None
    state_class: Optional[str] = None
    unit: Optional[str] = None
    precision: Optional[int] = None
    category: Optional[EntityCategory] = None
    attributes_fn: Optional[Callable] = None
    
    def create_sensor(self, updater) -> 'OptimizedEveusSensor':
        """Create sensor instance from specification."""
        return OptimizedEveusSensor(updater, self)

class OptimizedEveusSensor(EveusSensorBase):
    """High-performance templated sensor with caching and optimization."""
    
    def __init__(self, updater, spec: SensorSpec):
        """Initialize optimized sensor."""
        self.ENTITY_NAME = spec.name
        super().__init__(updater)
        
        self._spec = spec
        self._cached_value = None
        self._cache_timestamp = 0
        self._cache_ttl = 30  # 30 seconds cache TTL
        
        # Apply spec attributes efficiently
        if spec.icon:
            self._attr_icon = spec.icon
        if spec.device_class:
            self._attr_device_class = spec.device_class
        if spec.state_class:
            self._attr_state_class = spec.state_class
        if spec.unit:
            self._attr_native_unit_of_measurement = spec.unit
        if spec.precision is not None:
            self._attr_suggested_display_precision = spec.precision
        if spec.category:
            self._attr_entity_category = spec.category

    @property
    def native_value(self) -> Any:
        """Return cached or computed sensor value."""
        current_time = time.time()
        
        # Use cache for non-critical sensors
        if (self._spec.sensor_type != SensorType.CALCULATED and 
            self._cached_value is not None and 
            current_time - self._cache_timestamp < self._cache_ttl):
            return self._cached_value
            
        try:
            value = self._spec.value_fn(self._updater, self.hass)
            
            # Cache the value
            self._cached_value = value
            self._cache_timestamp = current_time
            
            return value
        except Exception as err:
            _LOGGER.error("Error getting value for %s: %s", self.name, err)
            return self._cached_value  # Return cached value on error

    @property 
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return cached or computed attributes."""
        if self._spec.attributes_fn:
            try:
                return self._spec.attributes_fn(self._updater, self.hass)
            except Exception as err:
                _LOGGER.error("Error getting attributes for %s: %s", self.name, err)
        return {}

# Optimized value functions with caching
@lru_cache(maxsize=32)
def _get_numeric_value(data: tuple, key: str, precision: int = None) -> float:
    """Cached numeric value extraction."""
    data_dict = dict(data)  # Convert tuple back to dict for lookup
    value = get_safe_value(data_dict, key)
    if value is None:
        return None
    return round(value, precision) if precision is not None else value

def _make_data_hashable(data: dict) -> tuple:
    """Convert dict to hashable tuple for caching."""
    return tuple(sorted(data.items()))

# Efficient value functions using partial application
def get_voltage(updater, hass) -> float:
    """Get voltage with caching.""" 
    return _get_numeric_value(_make_data_hashable(updater.data), "voltMeas1", 0)

def get_current(updater, hass) -> float:
    """Get current with caching."""
    return _get_numeric_value(_make_data_hashable(updater.data), "curMeas1", 1)

def get_power(updater, hass) -> float: 
    """Get power with caching."""
    return _get_numeric_value(_make_data_hashable(updater.data), "powerMeas", 1)

def get_current_set(updater, hass) -> float:
    """Get current set with caching."""
    return _get_numeric_value(_make_data_hashable(updater.data), "currentSet", 0)

def get_session_energy(updater, hass) -> float:
    """Get session energy with caching."""
    return _get_numeric_value(_make_data_hashable(updater.data), "sessionEnergy", 2)

def get_total_energy(updater, hass) -> float:
    """Get total energy with caching."""
    return _get_numeric_value(_make_data_hashable(updater.data), "totalEnergy", 2)

def get_counter_a_energy(updater, hass) -> float:
    """Get counter A energy with caching."""
    return _get_numeric_value(_make_data_hashable(updater.data), "IEM1", 2)

def get_counter_a_cost(updater, hass) -> float:
    """Get counter A cost with caching."""
    return _get_numeric_value(_make_data_hashable(updater.data), "IEM1_money", 2)

def get_counter_b_energy(updater, hass) -> float:
    """Get counter B energy with caching."""
    return _get_numeric_value(_make_data_hashable(updater.data), "IEM2", 2)

def get_counter_b_cost(updater, hass) -> float:
    """Get counter B cost with caching."""
    return _get_numeric_value(_make_data_hashable(updater.data), "IEM2_money", 2)

def get_box_temperature(updater, hass) -> float:
    """Get box temperature with caching."""
    return _get_numeric_value(_make_data_hashable(updater.data), "temperature1", 0)

def get_plug_temperature(updater, hass) -> float:
    """Get plug temperature with caching."""
    return _get_numeric_value(_make_data_hashable(updater.data), "temperature2", 0)

def get_battery_voltage(updater, hass) -> float:
    """Get battery voltage with caching."""
    return _get_numeric_value(_make_data_hashable(updater.data), "vBat", 2)

# State functions with caching
@lru_cache(maxsize=16)
def get_charger_state(updater, hass) -> str:
    """Get charger state with caching."""
    state_value = get_safe_value(updater.data, "state", int)
    return get_charging_state(state_value) if state_value is not None else None

@lru_cache(maxsize=16) 
def get_charger_substate(updater, hass) -> str:
    """Get charger substate with caching."""
    state = get_safe_value(updater.data, "state", int)
    substate = get_safe_value(updater.data, "subState", int)
    
    if None in (state, substate):
        return None
        
    if state == 7:  # Error state
        return get_error_state(substate)
    return get_normal_substate(substate)

@lru_cache(maxsize=8)
def get_ground_status(updater, hass) -> str:
    """Get ground status with caching."""
    value = get_safe_value(updater.data, "ground", int)
    return "Connected" if value == 1 else "Not Connected" if value == 0 else None

# Time and session functions
def get_session_time(updater, hass) -> str:
    """Get formatted session time."""
    seconds = get_safe_value(updater.data, "sessionTime", int)
    return format_duration(seconds) if seconds is not None else None

def get_session_time_attrs(updater, hass) -> dict:
    """Get session time attributes."""
    seconds = get_safe_value(updater.data, "sessionTime", int)
    return {"duration_seconds": seconds} if seconds is not None else {}

@lru_cache(maxsize=16)
def get_system_time(updater, hass) -> str:
    """Get system time with timezone correction and caching."""
    try:
        timestamp = get_safe_value(updater.data, "systemTime", int)
        if timestamp is None:
            return None
            
        # Get HA timezone
        ha_timezone = hass.config.time_zone
        if not ha_timezone:
            return None

        # Convert with timezone handling
        dt_utc = datetime.fromtimestamp(timestamp, tz=pytz.UTC)
        local_tz = pytz.timezone(ha_timezone)
        
        # Apply DST correction
        offset = 7200  # Base offset
        if is_dst(ha_timezone, dt_utc):
            offset += 3600
        
        corrected_timestamp = timestamp - offset
        dt_corrected = datetime.fromtimestamp(corrected_timestamp, tz=pytz.UTC)
        dt_local = dt_corrected.astimezone(local_tz)
        
        return dt_local.strftime("%H:%M")
            
    except Exception as err:
        _LOGGER.error("Error getting system time: %s", err)
        return None

# Rate and cost functions
def get_primary_rate_cost(updater, hass) -> float:
    """Get primary rate cost."""
    value = get_safe_value(updater.data, "tarif", float)
    return round(value / 100, 2) if value is not None else None

def get_active_rate_cost(updater, hass) -> float:
    """Get active rate cost with logic optimization."""
    active_rate = get_safe_value(updater.data, "activeTarif", int)
    if active_rate is None:
        return None

    # Use mapping for efficiency
    rate_keys = {0: "tarif", 1: "tarifAValue", 2: "tarifBValue"}
    key = rate_keys.get(active_rate)
    if not key:
        return None
        
    value = get_safe_value(updater.data, key, float)
    return round(value / 100, 2) if value is not None else None

def get_active_rate_attrs(updater, hass) -> dict:
    """Get active rate attributes."""
    active_rate = get_safe_value(updater.data, "activeTarif", int)
    return {"rate_name": RATE_STATES.get(active_rate, "Unknown")} if active_rate is not None else {}

def get_rate2_cost(updater, hass) -> float:
    """Get rate 2 cost.""" 
    value = get_safe_value(updater.data, "tarifAValue", float)
    return round(value / 100, 2) if value is not None else None

def get_rate3_cost(updater, hass) -> float:
    """Get rate 3 cost."""
    value = get_safe_value(updater.data, "tarifBValue", float)
    return round(value / 100, 2) if value is not None else None

def get_rate_status(rate_key: str):
    """Factory function for rate status sensors."""
    def _get_rate_status(updater, hass) -> str:
        enabled = get_safe_value(updater.data, rate_key, int)
        return "Enabled" if enabled == 1 else "Disabled" if enabled == 0 else None
    return _get_rate_status

# Network quality functions (optimized)
def get_connection_quality(updater, hass) -> float:
    """Get connection quality as numeric value."""
    try:
        if hasattr(updater, '_network') and hasattr(updater._network, 'connection_quality'):
            metrics = updater._network.connection_quality
            return round(max(0, min(100, metrics.get('success_rate', 0))))
        return 100  # Default to 100% if no metrics available
    except Exception as err:
        _LOGGER.error("Error getting connection quality: %s", err)
        return 0

def get_connection_attrs(updater, hass) -> dict:
    """Get optimized connection attributes."""
    try:
        if not hasattr(updater, '_network'):
            return {"status": "Unknown"}
            
        metrics = updater._network.connection_quality
        success_rate = metrics.get('success_rate', 100)
        
        # Simplified attributes for better performance
        return {
            "connection_quality": f"{round(success_rate)}%",
            "latency_avg": f"{max(0, metrics.get('latency_avg', 0)):.2f}s",
            "recent_errors": metrics.get('recent_errors', 0),
            "status": "Excellent" if success_rate > 95 else 
                    "Good" if success_rate > 80 else
                    "Fair" if success_rate > 60 else
                    "Poor" if success_rate > 30 else "Critical"
        }
        
    except Exception as err:
        _LOGGER.error("Error getting connection attributes: %s", err)
        return {"status": "Error"}

# Sensor specification factory - creates all sensors efficiently
def create_sensor_specifications() -> List[SensorSpec]:
    """Create all sensor specifications efficiently using factory pattern."""
    
    # Measurement sensors - created programmatically
    measurements = [
        ("Voltage", get_voltage, "mdi:flash", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, 0),
        ("Current", get_current, "mdi:current-ac", SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE, 1), 
        ("Power", get_power, "mdi:flash", SensorDeviceClass.POWER, UnitOfPower.WATT, 1),
        ("Current Set", get_current_set, "mdi:current-ac", SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE, 0),
    ]
    
    measurement_specs = [
        SensorSpec(
            key=name.lower().replace(" ", "_"),
            name=name,
            value_fn=fn,
            sensor_type=SensorType.MEASUREMENT,
            icon=icon,
            device_class=device_class,
            state_class=SensorStateClass.MEASUREMENT,
            unit=unit,
            precision=precision
        ) for name, fn, icon, device_class, unit, precision in measurements
    ]
    
    # Energy sensors - created programmatically
    energy_sensors = [
        ("Session Energy", get_session_energy, "mdi:transmission-tower-export", SensorStateClass.TOTAL),
        ("Total Energy", get_total_energy, "mdi:transmission-tower", SensorStateClass.TOTAL_INCREASING),
        ("Counter A Energy", get_counter_a_energy, "mdi:counter", SensorStateClass.TOTAL_INCREASING),
        ("Counter B Energy", get_counter_b_energy, "mdi:counter", SensorStateClass.TOTAL_INCREASING),
    ]
    
    energy_specs = [
        SensorSpec(
            key=name.lower().replace(" ", "_"),
            name=name,
            value_fn=fn,
            sensor_type=SensorType.ENERGY,
            icon=icon,
            device_class=SensorDeviceClass.ENERGY,
            state_class=state_class,
            unit=UnitOfEnergy.KILO_WATT_HOUR,
            precision=2
        ) for name, fn, icon, state_class in energy_sensors
    ]
    
    # Diagnostic sensors - created programmatically
    diagnostic_sensors = [
        ("State", get_charger_state, "mdi:state-machine"),
        ("Substate", get_charger_substate, "mdi:information-variant"),
        ("Ground", get_ground_status, "mdi:electric-switch"),
        ("Box Temperature", get_box_temperature, "mdi:thermometer", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 0),
        ("Plug Temperature", get_plug_temperature, "mdi:thermometer-high", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 0),
        ("Battery Voltage", get_battery_voltage, "mdi:battery", SensorDeviceClass.VOLTAGE, "V", 2),
        ("System Time", get_system_time, "mdi:clock-outline"),
    ]
    
    diagnostic_specs = [
        SensorSpec(
            key=name.lower().replace(" ", "_"),
            name=name,
            value_fn=fn,
            sensor_type=SensorType.DIAGNOSTIC,
            icon=icon,
            device_class=device_class if len(item) > 3 else None,
            state_class=SensorStateClass.MEASUREMENT if len(item) > 3 and device_class else None,
            unit=unit if len(item) > 4 else None,
            precision=precision if len(item) > 5 else None,
            category=EntityCategory.DIAGNOSTIC
        ) for item in diagnostic_sensors 
        for name, fn, icon, *rest in [item]
        for device_class, unit, precision in [rest + [None, None, None]][:1]
    ]
    
    # Special sensors with individual specifications
    special_specs = [
        SensorSpec(
            key="session_time",
            name="Session Time", 
            value_fn=get_session_time,
            sensor_type=SensorType.STATE,
            icon="mdi:timer",
            attributes_fn=get_session_time_attrs
        ),
        SensorSpec(
            key="counter_a_cost",
            name="Counter A Cost",
            value_fn=get_counter_a_cost,
            sensor_type=SensorType.ENERGY,
            icon="mdi:currency-uah",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit="₴",
            precision=2
        ),
        SensorSpec(
            key="counter_b_cost", 
            name="Counter B Cost",
            value_fn=get_counter_b_cost,
            sensor_type=SensorType.ENERGY,
            icon="mdi:currency-uah",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit="₴",
            precision=2
        ),
        SensorSpec(
            key="primary_rate_cost",
            name="Primary Rate Cost",
            value_fn=get_primary_rate_cost,
            sensor_type=SensorType.STATE,
            icon="mdi:currency-uah",
            state_class=SensorStateClass.MEASUREMENT,
            unit="₴/kWh",
            precision=2
        ),
        SensorSpec(
            key="active_rate_cost",
            name="Active Rate Cost", 
            value_fn=get_active_rate_cost,
            sensor_type=SensorType.STATE,
            icon="mdi:currency-uah",
            state_class=SensorStateClass.MEASUREMENT,
            unit="₴/kWh",
            precision=2,
            attributes_fn=get_active_rate_attrs
        ),
        SensorSpec(
            key="rate_2_cost",
            name="Rate 2 Cost",
            value_fn=get_rate2_cost,
            sensor_type=SensorType.STATE,
            icon="mdi:currency-uah",
            state_class=SensorStateClass.MEASUREMENT,
            unit="₴/kWh", 
            precision=2
        ),
        SensorSpec(
            key="rate_3_cost",
            name="Rate 3 Cost",
            value_fn=get_rate3_cost,
            sensor_type=SensorType.STATE,
            icon="mdi:currency-uah",
            state_class=SensorStateClass.MEASUREMENT,
            unit="₴/kWh",
            precision=2
        ),
        SensorSpec(
            key="rate_2_status",
            name="Rate 2 Status",
            value_fn=get_rate_status("tarifAEnable"),
            sensor_type=SensorType.STATE,
            icon="mdi:clock-check"
        ),
        SensorSpec(
            key="rate_3_status", 
            name="Rate 3 Status",
            value_fn=get_rate_status("tarifBEnable"),
            sensor_type=SensorType.STATE,
            icon="mdi:clock-check"
        ),
        SensorSpec(
            key="connection_quality",
            name="Connection Quality",
            value_fn=get_connection_quality,
            sensor_type=SensorType.DIAGNOSTIC,
            icon="mdi:connection",
            state_class=SensorStateClass.MEASUREMENT,
            unit="%",
            precision=0,
            category=EntityCategory.DIAGNOSTIC,
            attributes_fn=get_connection_attrs
        ),
    ]
    
    return measurement_specs + energy_specs + diagnostic_specs + special_specs

def get_sensor_specifications() -> List[SensorSpec]:
    """Get all sensor specifications (cached for performance)."""
    return create_sensor_specifications()
