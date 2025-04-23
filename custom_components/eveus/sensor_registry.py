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
    PERCENTAGE # Import PERCENTAGE constant
)
from homeassistant.helpers.entity import EntityCategory
import pytz

from .common import EveusSensorBase # Import base class
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

# Forward declaration for type hints if EveusTemplatedSensor is defined below
# This avoids NameError if used in SensorDefinition before its definition
class EveusTemplatedSensor(EveusSensorBase): pass

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
        precision: Optional[int] = None, # Correct parameter name
        category: Optional[EntityCategory] = None,
        attributes_fn: Optional[Callable] = None,
        # Default sensor_class to None, it will be handled below
        sensor_class: Optional[Type[EveusSensorBase]] = None,
    ):
        """Initialize sensor definition."""
        self.entity_name = entity_name
        self.value_fn = value_fn
        self.icon = icon
        self.device_class = device_class
        self.state_class = state_class
        self.unit = unit
        self.precision = precision # Store the precision
        self.category = category
        self.attributes_fn = attributes_fn
        # Correctly default to EveusTemplatedSensor if no specific class is provided
        self.sensor_class = sensor_class or EveusTemplatedSensor

    def create_sensor(self, updater):
        """Create a sensor instance from this definition."""
        sensor_cls = self.sensor_class
        # Pass both updater and the definition itself to the constructor
        # EveusTemplatedSensor expects this, custom classes might too.
        return sensor_cls(updater, self)


class EveusTemplatedSensor(EveusSensorBase):
    """Templated sensor based on definitions."""

    # Change constructor to accept definition
    def __init__(self, updater, definition: SensorDefinition):
        """Initialize the sensor with a definition."""
        # Set ENTITY_NAME before calling super().__init__
        self.ENTITY_NAME = definition.entity_name
        # Call the base class constructor (EveusSensorBase)
        # It only expects 'updater'
        super().__init__(updater)

        self._definition = definition
        # Keep track of the last known value to avoid unnecessary updates if desired
        self._last_value = None

        # Apply definition attributes directly using _attr_ prefix
        if definition.icon:
            self._attr_icon = definition.icon
        if definition.device_class:
            self._attr_device_class = definition.device_class
        if definition.state_class:
            self._attr_state_class = definition.state_class
        if definition.unit:
            self._attr_native_unit_of_measurement = definition.unit
        # Use suggested_display_precision for formatting hints in HA frontend
        # This is set based on the 'precision' from the definition
        if definition.precision is not None:
            self._attr_suggested_display_precision = definition.precision
        if definition.category:
            self._attr_entity_category = definition.category

    @property
    def native_value(self) -> Any:
        """Return the sensor value from definition's value function."""
        try:
            # Call the value function defined in the SensorDefinition
            new_value = self._definition.value_fn(self._updater, self.hass)
            self._last_value = new_value # Store the latest value
            return new_value
        except Exception as err:
            # Log error and return the last known value or None
            _LOGGER.error("Error getting value for %s: %s", self.name, err)
            return self._last_value # Return last good value during error

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes if an attributes function is defined."""
        attributes = {} # Start with empty dict

        if self._definition.attributes_fn:
            try:
                # Get attributes from the definition's attributes function
                custom_attributes = self._definition.attributes_fn(self._updater, self.hass)
                if isinstance(custom_attributes, dict):
                    attributes.update(custom_attributes)
                else:
                     _LOGGER.warning("Attributes function for %s did not return a dict.", self.name)
            except Exception as err:
                _LOGGER.error("Error getting attributes for %s: %s", self.name, err)
                attributes["error"] = f"Failed to retrieve attributes: {err}" # Add error info
        return attributes


# --- Sensor Value Functions ---

def get_voltage(updater, hass) -> float | None:
    """Get voltage value."""
    value = get_safe_value(updater.data, "voltMeas1", float)
    return round(value, 0) if value is not None else None

def get_current(updater, hass) -> float | None:
    """Get current value."""
    value = get_safe_value(updater.data, "curMeas1", float)
    return round(value, 1) if value is not None else None

def get_power(updater, hass) -> float | None:
    """Get power value."""
    value = get_safe_value(updater.data, "powerMeas", float)
    # Ensure power is non-negative
    return max(0.0, round(value, 1)) if value is not None else None

def get_current_set(updater, hass) -> float | None:
    """Get current set value."""
    value = get_safe_value(updater.data, "currentSet", float)
    return round(value, 0) if value is not None else None

def get_session_time(updater, hass) -> int | None:
    """Get session time in seconds."""
    # Return raw seconds for duration sensor state
    seconds = get_safe_value(updater.data, "sessionTime", int)
    return max(0, seconds) if seconds is not None else None

def get_session_time_attrs(updater, hass) -> dict:
    """Get session time attributes (formatted duration)."""
    seconds = get_safe_value(updater.data, "sessionTime", int)
    attrs = {}
    if seconds is not None:
        attrs["formatted_duration"] = format_duration(max(0, seconds))
    return attrs

def get_session_energy(updater, hass) -> float | None:
    """Get session energy."""
    value = get_safe_value(updater.data, "sessionEnergy", float)
    return round(value, 2) if value is not None else None

def get_total_energy(updater, hass) -> float | None:
    """Get total energy."""
    value = get_safe_value(updater.data, "totalEnergy", float)
    return round(value, 2) if value is not None else None

def get_counter_a_energy(updater, hass) -> float | None:
    """Get counter A energy."""
    value = get_safe_value(updater.data, "IEM1", float)
    return round(value, 2) if value is not None else None

def get_counter_a_cost(updater, hass) -> float | None:
    """Get counter A cost."""
    value = get_safe_value(updater.data, "IEM1_money", float)
    # Assume value is in smallest currency unit (e.g., cents, kopecks)
    return round(value / 100, 2) if value is not None else None

def get_counter_b_energy(updater, hass) -> float | None:
    """Get counter B energy."""
    value = get_safe_value(updater.data, "IEM2", float)
    return round(value, 2) if value is not None else None

def get_counter_b_cost(updater, hass) -> float | None:
    """Get counter B cost."""
    value = get_safe_value(updater.data, "IEM2_money", float)
    # Assume value is in smallest currency unit (e.g., cents, kopecks)
    return round(value / 100, 2) if value is not None else None

def get_charger_state(updater, hass) -> str | None:
    """Get charger state."""
    state_value = get_safe_value(updater.data, "state", int)
    if state_value is not None:
        return CHARGING_STATES.get(state_value, f"Unknown State ({state_value})")
    return None

def get_charger_substate(updater, hass) -> str | None:
    """Get charger substate."""
    state = get_safe_value(updater.data, "state", int)
    substate = get_safe_value(updater.data, "subState", int)

    if state is None or substate is None:
        return None

    if state == 7:  # Error state
        return ERROR_STATES.get(substate, f"Unknown Error ({substate})")
    return NORMAL_SUBSTATES.get(substate, f"Unknown Substate ({substate})")

def get_ground_status(updater, hass) -> str | None:
    """Get ground status."""
    value = get_safe_value(updater.data, "ground", int)
    if value is not None:
        return "Connected" if value == 1 else "Not Connected"
    return None

def get_box_temperature(updater, hass) -> float | None:
    """Get box temperature."""
    return get_safe_value(updater.data, "temperature1", float)

def get_plug_temperature(updater, hass) -> float | None:
    """Get plug temperature."""
    return get_safe_value(updater.data, "temperature2", float)

def get_battery_voltage(updater, hass) -> float | None:
    """Get battery voltage."""
    value = get_safe_value(updater.data, "vBat", float)
    return round(value, 2) if value is not None else None

def get_system_time(updater, hass) -> datetime | None:
    """Get system time as datetime object."""
    # Return datetime object for timestamp sensor state
    try:
        timestamp = get_safe_value(updater.data, "systemTime", int)
        if timestamp is None or timestamp <= 0:
            return None

        # Assume device timestamp is UTC
        dt_device_utc = datetime.fromtimestamp(timestamp, tz=pytz.UTC)
        return dt_device_utc # Let HA handle timezone display

    except Exception as err:
        _LOGGER.error("Error processing system time: %s", err)
        return None

def get_primary_rate_cost(updater, hass) -> float | None:
    """Get primary rate cost."""
    value = get_safe_value(updater.data, "tarif", float)
    # Assuming value is in cents/kopecks per kWh
    return round(value / 100, 2) if value is not None else None

def get_active_rate_cost(updater, hass) -> float | None:
    """Get active rate cost."""
    try:
        active_rate = get_safe_value(updater.data, "activeTarif", int)
        if active_rate is None:
            return None

        value = None
        if active_rate == 0: # Primary
            value = get_safe_value(updater.data, "tarif", float)
        elif active_rate == 1: # Rate 2 (Tarif A)
            value = get_safe_value(updater.data, "tarifAValue", float)
        elif active_rate == 2: # Rate 3 (Tarif B)
            value = get_safe_value(updater.data, "tarifBValue", float)
        else:
            return None # Unknown rate

        # Assuming value is in cents/kopecks per kWh
        return round(value / 100, 2) if value is not None else None
    except Exception as err:
        _LOGGER.error("Error getting active rate cost: %s", err)
        return None

def get_active_rate_attrs(updater, hass) -> dict:
    """Get active rate attributes."""
    try:
        active_rate = get_safe_value(updater.data, "activeTarif", int)
        if active_rate is not None:
            return {"active_rate_name": RATE_STATES.get(active_rate, f"Unknown ({active_rate})")}
    except Exception as e:
        _LOGGER.debug("Could not determine active rate attributes: %s", e)
    return {}

def get_rate2_cost(updater, hass) -> float | None:
    """Get rate 2 cost."""
    value = get_safe_value(updater.data, "tarifAValue", float)
    return round(value / 100, 2) if value is not None else None

def get_rate3_cost(updater, hass) -> float | None:
    """Get rate 3 cost."""
    value = get_safe_value(updater.data, "tarifBValue", float)
    return round(value / 100, 2) if value is not None else None

def get_rate_status(updater, hass, enable_key: str) -> str | None:
    """Helper to get rate status (Enabled/Disabled)."""
    enabled = get_safe_value(updater.data, enable_key, int)
    if enabled is None:
        return None
    return "Enabled" if enabled == 1 else "Disabled"

def get_rate2_status(updater, hass) -> str | None:
    """Get rate 2 status."""
    return get_rate_status(updater, hass, "tarifAEnable")

def get_rate3_status(updater, hass) -> str | None:
    """Get rate 3 status."""
    return get_rate_status(updater, hass, "tarifBEnable")

# --- Connection Quality Functions ---

def get_connection_quality(updater, hass) -> float | None:
    """Get connection quality success rate as percentage."""
    try:
        # Access NetworkManager instance via updater
        metrics = updater._network.connection_quality
        # Ensure value is between 0 and 100
        quality = round(max(0.0, min(100.0, metrics.get('success_rate', 100.0))))
        return quality
    except Exception as err:
        _LOGGER.error("Error getting connection quality: %s", err)
        return None # Or return 0 if unavailable

def get_connection_attrs(updater, hass) -> dict:
    """Get enhanced connection quality attributes."""
    attrs = {}
    try:
        # Access NetworkManager instance via updater
        network_manager = updater._network
        metrics = network_manager.connection_quality
        quality_details = network_manager._quality_metrics # Access raw metrics
        now = time.time()

        # Basic metrics
        attrs["average_latency_ms"] = round(metrics.get('latency_avg', 0) * 1000)
        attrs["requests_per_minute"] = round(metrics.get('requests_per_minute', 0))
        attrs["recent_errors_count"] = metrics.get('recent_errors', 0)

        # Success rate and status
        success_rate = metrics.get('success_rate', 100.0)
        status = "Excellent" if success_rate > 95 else \
                 "Good" if success_rate > 80 else \
                 "Fair" if success_rate > 60 else \
                 "Poor" if success_rate > 30 else "Critical"
        attrs["status"] = status

        # Last successful connection and uptime
        last_success_ts = quality_details.get('last_successful_connection')
        if last_success_ts:
            last_success_dt = datetime.fromtimestamp(last_success_ts)
            attrs["last_successful_connection"] = last_success_dt.isoformat()
            attrs["time_since_last_success"] = format_duration(int(now - last_success_ts))
        else:
            attrs["last_successful_connection"] = "Never"
            attrs["time_since_last_success"] = "N/A"

        # Last errors details
        last_errors = list(quality_details.get('last_errors', []))
        if last_errors:
            formatted_errors = []
            for err in reversed(last_errors): # Show newest first
                error_time = datetime.fromtimestamp(err.get('timestamp', now))
                error_age = format_duration(int(now - err.get('timestamp', now)))
                formatted_errors.append(
                    f"{error_time.strftime('%H:%M:%S')} ({error_age} ago): {err.get('type', 'Unknown')}"
                )
            attrs["last_errors"] = formatted_errors
            # Add details of the very last error
            last_error_details = last_errors[-1]
            attrs["last_error_type"] = last_error_details.get('type', 'Unknown')
            attrs["last_error_time"] = datetime.fromtimestamp(last_error_details.get('timestamp', now)).isoformat()
        else:
            attrs["last_errors"] = []
            attrs["last_error_type"] = "None"
            attrs["last_error_time"] = "N/A"

        # Error type counts
        error_counts = quality_details.get('error_types')
        if error_counts:
             attrs["error_type_counts"] = dict(error_counts)

        # Optional: Success Rate History (can make attributes large)
        # attrs["success_rate_history"] = list(quality_details.get('success_rate_history', []))

    except Exception as err:
        _LOGGER.error("Error getting connection attributes: %s", err)
        attrs["error"] = f"Failed to retrieve attributes: {err}"

    return attrs


# --- Sensor Definitions Registry ---

SENSOR_DEFINITIONS = [
    # --- Basic Sensors ---
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
        state_class=SensorStateClass.MEASUREMENT, # Not strictly measurement, but represents a setting
        unit=UnitOfElectricCurrent.AMPERE,
        precision=0,
        category=EntityCategory.CONFIG # Configurable value
    ),
    SensorDefinition(
        entity_name="Session Time",
        value_fn=get_session_time, # Returns seconds
        icon="mdi:timer-outline", # Updated icon
        attributes_fn=get_session_time_attrs, # Attribute for formatted string
        device_class=SensorDeviceClass.DURATION, # Use duration device class
        unit="s", # Base unit for duration is seconds
        state_class=SensorStateClass.TOTAL, # Represents total duration for session
        precision=0, # Use correct parameter name 'precision'
    ),
    SensorDefinition(
        entity_name="Session Energy",
        value_fn=get_session_energy,
        icon="mdi:lightning-bolt-circle", # Updated icon
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL, # Energy for current session
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        precision=2,
    ),
    SensorDefinition(
        entity_name="Total Energy",
        value_fn=get_total_energy,
        icon="mdi:meter-electric", # Updated icon
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING, # Always increasing total
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        precision=2,
    ),

    # --- Counter Sensors ---
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
        icon="mdi:currency-usd", # Changed to generic currency icon
        device_class=SensorDeviceClass.MONETARY, # Use monetary device class
        state_class=SensorStateClass.TOTAL_INCREASING,
        # unit="USD", # Unit should be set based on HA currency settings ideally, fallback
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
        icon="mdi:currency-usd", # Changed to generic currency icon
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        # unit="USD",
        precision=2,
    ),

    # --- Diagnostic Sensors ---
    SensorDefinition(
        entity_name="State",
        value_fn=get_charger_state,
        icon="mdi:state-machine",
        category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM, # Represents distinct states
        # options=list(CHARGING_STATES.values()) # Optional: provide possible states
    ),
    SensorDefinition(
        entity_name="Substate",
        value_fn=get_charger_substate,
        icon="mdi:information-outline", # Updated icon
        category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        # options=list(NORMAL_SUBSTATES.values()) + list(ERROR_STATES.values()) # Optional
    ),
    SensorDefinition(
        entity_name="Ground Status", # Renamed from "Ground"
        value_fn=get_ground_status,
        icon="mdi:earth", # Updated icon
        category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        # options=["Connected", "Not Connected"] # Optional
    ),
    SensorDefinition(
        entity_name="Box Temperature",
        value_fn=get_box_temperature,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfTemperature.CELSIUS,
        precision=1, # Increased precision slightly
        category=EntityCategory.DIAGNOSTIC,
    ),
    SensorDefinition(
        entity_name="Plug Temperature",
        value_fn=get_plug_temperature,
        icon="mdi:thermometer-lines", # Updated icon
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfTemperature.CELSIUS,
        precision=1, # Increased precision slightly
        category=EntityCategory.DIAGNOSTIC,
    ),
    SensorDefinition(
        entity_name="Internal Battery Voltage", # Renamed for clarity
        value_fn=get_battery_voltage,
        icon="mdi:battery-heart-variant", # Updated icon
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfElectricPotential.VOLT, # Corrected unit
        precision=2,
        category=EntityCategory.DIAGNOSTIC,
    ),
    SensorDefinition(
        entity_name="Device Time", # Renamed from "System Time"
        value_fn=get_system_time, # Returns datetime object
        icon="mdi:clock-outline",
        category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.TIMESTAMP # Use timestamp device class
    ),
    SensorDefinition(
        entity_name="Connection Quality",
        value_fn=get_connection_quality, # Function for main state (percentage)
        icon="mdi:signal-variant", # Updated icon
        state_class=SensorStateClass.MEASUREMENT,
        unit=PERCENTAGE, # Use HA constant for percentage
        precision=0,
        category=EntityCategory.DIAGNOSTIC,
        attributes_fn=get_connection_attrs, # Function for detailed attributes
    ),

    # --- Rate Sensors ---
    SensorDefinition(
        entity_name="Primary Rate Cost",
        value_fn=get_primary_rate_cost,
        icon="mdi:currency-usd",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT, # Cost is a measurement
        # unit="USD/kWh", # Define unit clearly
        precision=2, # Or more precision if needed (e.g., 3 for $0.123)
        category=EntityCategory.CONFIG, # Related to configuration
    ),
    SensorDefinition(
        entity_name="Active Rate Cost",
        value_fn=get_active_rate_cost,
        icon="mdi:currency-usd-circle", # Updated icon
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        # unit="USD/kWh",
        precision=2,
        attributes_fn=get_active_rate_attrs,
        category=EntityCategory.CONFIG,
    ),
    SensorDefinition(
        entity_name="Rate 2 Cost",
        value_fn=get_rate2_cost,
        icon="mdi:currency-usd",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        # unit="USD/kWh",
        precision=2,
        category=EntityCategory.CONFIG,
    ),
    SensorDefinition(
        entity_name="Rate 3 Cost",
        value_fn=get_rate3_cost,
        icon="mdi:currency-usd",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        # unit="USD/kWh",
        precision=2,
        category=EntityCategory.CONFIG,
    ),
    SensorDefinition(
        entity_name="Rate 2 Status",
        value_fn=get_rate2_status,
        icon="mdi:calendar-clock", # Updated icon
        category=EntityCategory.CONFIG,
        device_class=SensorDeviceClass.ENUM,
        # options=["Enabled", "Disabled"]
    ),
    SensorDefinition(
        entity_name="Rate 3 Status",
        value_fn=get_rate3_status,
        icon="mdi:calendar-clock",
        category=EntityCategory.CONFIG,
        device_class=SensorDeviceClass.ENUM,
        # options=["Enabled", "Disabled"]
    ),
]

def get_sensor_definitions() -> List[SensorDefinition]:
    """Get all sensor definitions."""
    return SENSOR_DEFINITIONS
