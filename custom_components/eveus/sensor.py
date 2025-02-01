"""Support for Eveus sensors."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.components.text import TextEntity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfPower,
    UnitOfEnergy,
    UnitOfTemperature,
    UnitOfTime,
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
)

from .base import EveusBaseConnection, EveusBaseEntity
from .const import (
    DOMAIN,
    CHARGING_STATES,
    ERROR_STATES,
    NORMAL_SUBSTATES,
    ATTR_VOLTAGE,
    ATTR_CURRENT,
    ATTR_POWER,
    ATTR_SESSION_ENERGY,
    ATTR_TOTAL_ENERGY,
    ATTR_SESSION_TIME,
    ATTR_STATE,
    ATTR_SUBSTATE,
    ATTR_CURRENT_SET,
    ATTR_ENABLED,
    ATTR_TEMPERATURE_BOX,
    ATTR_TEMPERATURE_PLUG,
    ATTR_SYSTEM_TIME,
    ATTR_COUNTER_A_ENERGY,
    ATTR_COUNTER_B_ENERGY,
    ATTR_COUNTER_A_COST,
    ATTR_COUNTER_B_COST,
    ATTR_GROUND,
    ATTR_BATTERY_VOLTAGE,
)
from .helpers import format_duration

_LOGGER = logging.getLogger(__name__)

class EveusBaseSensor(EveusBaseEntity, SensorEntity, RestoreEntity):
    """Base sensor for Eveus integration."""

    def __init__(self, connection: EveusBaseConnection, name: str, unique_id_suffix: str) -> None:
        """Initialize the sensor."""
        super().__init__(connection)
        self._attr_name = name
        self._attr_unique_id = f"{connection._host}_{unique_id_suffix}"
        self._previous_value = None

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and state.state not in ('unknown', 'unavailable'):
            try:
                if hasattr(self, '_attr_suggested_display_precision'):
                    self._previous_value = float(state.state)
                else:
                    self._previous_value = state.state
            except (TypeError, ValueError):
                self._previous_value = state.state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {}
        if self._previous_value is not None:
            attrs["previous_value"] = self._previous_value
        return attrs

class EveusNumericSensor(EveusBaseSensor):
    """Base class for numeric sensors."""
    
    _attr_suggested_display_precision = 2
    _key: str = None

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        try:
            value = float(self._connection.state_data.get(self._key, 0))
            self._previous_value = value
            return round(value, self._attr_suggested_display_precision)
        except (TypeError, ValueError):
            return self._previous_value

class EveusEnergyBaseSensor(EveusNumericSensor):
    """Base energy sensor with improved precision."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1

class EveusVoltageSensor(EveusNumericSensor):
    """Voltage sensor."""
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:lightning-bolt"
    _attr_suggested_display_precision = 0
    _key = ATTR_VOLTAGE

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Voltage", "voltage")

class EveusCurrentSensor(EveusNumericSensor):
    """Current sensor."""
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:current-ac"
    _attr_suggested_display_precision = 1
    _key = ATTR_CURRENT

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Current", "current")

class EveusPowerSensor(EveusNumericSensor):
    """Power sensor."""
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:flash"
    _attr_suggested_display_precision = 0
    _key = ATTR_POWER

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Power", "power")

class EveusCurrentSetSensor(EveusNumericSensor):
    """Current set sensor."""
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:current-ac"
    _key = ATTR_CURRENT_SET

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Current Set", "current_set")

class EveusSessionEnergySensor(EveusEnergyBaseSensor):
    """Session energy sensor."""
    _key = ATTR_SESSION_ENERGY
    _attr_icon = "mdi:battery-charging"

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Session Energy", "session_energy")

class EveusTotalEnergySensor(EveusEnergyBaseSensor):
    """Total energy sensor."""
    _key = ATTR_TOTAL_ENERGY
    _attr_icon = "mdi:battery-charging-100"

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Total Energy", "total_energy")

class EveusStateSensor(EveusBaseSensor):
    """Charging state sensor."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information"

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "State", "state")

    @property
    def native_value(self) -> str:
        """Return charging state."""
        try:
            return CHARGING_STATES.get(self._connection.state_data.get(ATTR_STATE, -1), "Unknown")
        except (TypeError, ValueError):
            return "Unknown"

class EveusSubstateSensor(EveusBaseSensor):
    """Substate sensor."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information"

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Substate", "substate")

    @property
    def native_value(self) -> str:
        """Return substate with context."""
        try:
            state = self._connection.state_data.get(ATTR_STATE)
            substate = self._connection.state_data.get(ATTR_SUBSTATE)
            
            if state == 7:  # Error state
                return ERROR_STATES.get(substate, "Unknown Error")
            return NORMAL_SUBSTATES.get(substate, "Unknown State")
        except (TypeError, ValueError):
            return "Unknown"

class EveusEnabledSensor(EveusBaseSensor):
    """Enabled state sensor."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:power"

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Enabled", "enabled")

    @property
    def native_value(self) -> str:
        """Return if charging is enabled."""
        try:
            return "Yes" if self._connection.state_data.get(ATTR_ENABLED) == 1 else "No"
        except (TypeError, ValueError):
            return "Unknown"

class EveusGroundSensor(EveusBaseSensor):
    """Ground sensor."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:electric-switch"

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Ground", "ground")

    @property
    def native_value(self) -> str:
        """Return ground status."""
        try:
            return "Connected" if self._connection.state_data.get(ATTR_GROUND) == 1 else "Not Connected"
        except (TypeError, ValueError):
            return "Unknown"

class EveusBoxTemperatureSensor(EveusNumericSensor):
    """Box temperature sensor."""
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:thermometer"
    _key = ATTR_TEMPERATURE_BOX

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Box Temperature", "box_temperature")

class EveusPlugTemperatureSensor(EveusNumericSensor):
    """Plug temperature sensor."""
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:thermometer-high"
    _key = ATTR_TEMPERATURE_PLUG

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Plug Temperature", "plug_temperature")

class EveusBatteryVoltageSensor(EveusNumericSensor):
    """Battery voltage sensor."""
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery"
    _key = ATTR_BATTERY_VOLTAGE

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Battery Voltage", "battery_voltage")

class EveusSystemTimeSensor(EveusBaseSensor):
    """System time sensor."""
    _attr_icon = "mdi:clock-outline"

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "System Time", "system_time")

    @property
    def native_value(self) -> str:
        """Return formatted system time."""
        try:
            timestamp = int(self._connection.state_data.get(ATTR_SYSTEM_TIME, 0))
            return datetime.fromtimestamp(timestamp).strftime("%H:%M")
        except (TypeError, ValueError):
            return "unknown"

class EveusSessionTimeSensor(EveusBaseSensor):
    """Session time sensor."""
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:timer"

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Session Time", "session_time")
    
    @property
    def native_value(self) -> int:
        """Return the session time in seconds."""
        try:
            return int(self._connection.state_data.get(ATTR_SESSION_TIME, 0))
        except (TypeError, ValueError):
            return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes
        try:
            seconds = int(self._connection.state_data.get(ATTR_SESSION_TIME, 0))
            attrs["formatted_time"] = format_duration(seconds)
        except (TypeError, ValueError):
            attrs["formatted_time"] = "0m"
        return attrs

class EveusCounterAEnergySensor(EveusEnergyBaseSensor):
    """Counter A energy sensor."""
    _key = ATTR_COUNTER_A_ENERGY
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:counter"

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Counter A Energy", "counter_a_energy")

class EveusCounterBEnergySensor(EveusEnergyBaseSensor):
    """Counter B energy sensor."""
    _key = ATTR_COUNTER_B_ENERGY
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:counter"

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Counter B Energy", "counter_b_energy")

class EveusCounterACostSensor(EveusNumericSensor):
    """Counter A cost sensor."""
    _attr_native_unit_of_measurement = "₴"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:currency-uah"
    _key = ATTR_COUNTER_A_COST

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Counter A Cost", "counter_a_cost")

class EveusCounterBCostSensor(EveusNumericSensor):
    """Counter B cost sensor."""
    _attr_native_unit_of_measurement = "₴"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:currency-uah"
    _key = ATTR_COUNTER_B_COST

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Counter B Cost", "counter_b_cost")

class EVSocKwhSensor(EveusBaseSensor):
    """EV State of Charge energy sensor."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:battery-charging"
    _attr_suggested_display_precision = 0
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "SOC Energy", "soc_kwh")

    @property
    def native_value(self) -> float | None:
        """Calculate and return state of charge in kWh."""
        try:
            initial_soc = float(self.hass.states.get("input_number.ev_initial_soc").state)
            max_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
            energy_charged = float(self._connection.state_data.get("IEM1", 0))
            correction = float(self.hass.states.get("input_number.ev_soc_correction").state)

            if initial_soc < 0 or initial_soc > 100 or max_capacity <= 0:
                return None

            initial_kwh = (initial_soc / 100) * max_capacity
            efficiency = (1 - correction / 100)
            charged_kwh = energy_charged * efficiency
            total_kwh = initial_kwh + charged_kwh
            
            return round(max(0, min(total_kwh, max_capacity)), 2)
        except (TypeError, ValueError, AttributeError):
            return None

class EVSocPercentSensor(EveusBaseSensor):
    """EV State of Charge percentage sensor."""
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:battery-charging"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "SOC Percent", "soc_percent")

    @property
    def native_value(self) -> float | None:
        """Return the state of charge percentage."""
        try:
            soc_kwh = float(self.hass.states.get("sensor.eveus_ev_charger_soc_energy").state)
            max_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
            
            if soc_kwh >= 0 and max_capacity > 0:
                percentage = round((soc_kwh / max_capacity * 100), 0)
                return max(0, min(percentage, 100))
            return None
        except (TypeError, ValueError, AttributeError):
            return None

class TimeToTargetSocSensor(EveusBaseSensor):
    """Time to target SOC sensor."""
    _attr_icon = "mdi:timer"

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the sensor."""
        super().__init__(connection, "Time to Target", "time_to_target")

    @property
    def native_value(self) -> str:
        """Calculate and return formatted time to target."""
        try:
            current_soc = float(self.hass.states.get("sensor.eveus_ev_charger_soc_percent").state)
            target_soc = float(self.hass.states.get("input_number.ev_target_soc").state)
            power_meas = float(self._connection.state_data.get(ATTR_POWER, 0))
            battery_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
            correction = float(self.hass.states.get("input_number.ev_soc_correction").state)

            if current_soc >= target_soc:
                return "Target reached"

            remaining_kwh = (target_soc - current_soc) * battery_capacity / 100
            efficiency = (1 - correction / 100)
            power_kw = power_meas * efficiency / 1000
            
            if power_kw <= 0:
                return "Not charging"

            total_minutes = round((remaining_kwh / power_kw * 60), 0)
            
            if total_minutes < 1:
                return "< 1m"

            days = int(total_minutes // 1440)
            hours = int((total_minutes % 1440) // 60)
            minutes = int(total_minutes % 60)

            parts = []
            if days > 0:
                parts.append(f"{days}d")
            if hours > 0:
                parts.append(f"{hours}h")
            if minutes > 0 or not parts:
                parts.append(f"{minutes}m")

            return " ".join(parts)

        except (TypeError, ValueError, AttributeError):
            return "Not charging"

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eveus sensors."""
    connection = EveusBaseConnection(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )

    # Create all sensor entities
    sensors = [
        # Basic measurements
        EveusVoltageSensor(connection),
        EveusCurrentSensor(connection),
        EveusPowerSensor(connection),
        EveusCurrentSetSensor(connection),
        EveusSessionEnergySensor(connection),
        EveusTotalEnergySensor(connection),
        
        # Diagnostic sensors
        EveusStateSensor(connection),
        EveusSubstateSensor(connection),
        EveusEnabledSensor(connection),
        EveusGroundSensor(connection),
        
        # Temperature sensors
        EveusBoxTemperatureSensor(connection),
        EveusPlugTemperatureSensor(connection),
        EveusBatteryVoltageSensor(connection),
        
        # Time and session sensors
        EveusSystemTimeSensor(connection),
        EveusSessionTimeSensor(connection),
        
        # Energy and cost counters
        EveusCounterAEnergySensor(connection),
        EveusCounterBEnergySensor(connection),
        EveusCounterACostSensor(connection),
        EveusCounterBCostSensor(connection),
        
        # EV-specific sensors
        EVSocKwhSensor(connection),
        EVSocPercentSensor(connection),
        TimeToTargetSocSensor(connection),
    ]

    # Initialize entities dict if needed
    if "entities" not in hass.data[DOMAIN][entry.entry_id]:
        hass.data[DOMAIN][entry.entry_id]["entities"] = {}

    # Store sensor references with unique_id as key
    hass.data[DOMAIN][entry.entry_id]["entities"]["sensor"] = {
        sensor.unique_id: sensor for sensor in sensors
    }

    async_add_entities(sensors)
