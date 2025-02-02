"""Support for Eveus sensors."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
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

from .common import (
    BaseEveusEntity,
    BaseEveusNumericEntity,
    EveusUpdater,
)
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

_LOGGER = logging.getLogger(__name__)

class EveusSensorBase(BaseEveusEntity, SensorEntity):
    """Base sensor with additional sensor-specific attributes."""

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_native_value = None

    @property
    def native_value(self) -> Any | None:
        """Return sensor value."""
        return self._attr_native_value

class EveusNumericSensor(EveusSensorBase):
    """Base class for numeric sensors."""

    _key: str = None
    _attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        try:
            value = self._updater.data.get(self._key)
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

class EveusDiagnosticSensor(BaseEveusEntity, SensorEntity):
    """Base diagnostic sensor."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information"

class EveusEnergyBaseSensor(EveusNumericSensor):
    """Base energy sensor with improved precision."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1

class EveusVoltageSensor(EveusNumericSensor):
    ENTITY_NAME = "Voltage"
    _key = ATTR_VOLTAGE
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:lightning-bolt"
    _attr_suggested_display_precision = 0

class EveusCurrentSensor(EveusNumericSensor):
    ENTITY_NAME = "Current"
    _key = ATTR_CURRENT
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:current-ac"
    _attr_suggested_display_precision = 1

class EveusPowerSensor(EveusNumericSensor):
    ENTITY_NAME = "Power"
    _key = ATTR_POWER
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:flash"
    _attr_suggested_display_precision = 0

class EveusCurrentSetSensor(EveusNumericSensor):
    ENTITY_NAME = "Current Set"
    _key = ATTR_CURRENT_SET
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:current-ac"
    _attr_suggested_display_precision = 0

class EveusSessionEnergySensor(EveusEnergyBaseSensor):
    ENTITY_NAME = "Session Energy"
    _key = ATTR_SESSION_ENERGY
    _attr_icon = "mdi:battery-charging"

class EveusTotalEnergySensor(EveusEnergyBaseSensor):
    ENTITY_NAME = "Total Energy"
    _key = ATTR_TOTAL_ENERGY
    _attr_icon = "mdi:battery-charging-100"

class EveusConnectionErrorsSensor(EveusDiagnosticSensor):
    """Failed requests counter sensor."""

    ENTITY_NAME = "Connection Errors"
    _attr_icon = "mdi:connection"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int:
        """Return number of consecutive failed requests."""
        return self._updater.failed_requests

class EveusStateSensor(EveusDiagnosticSensor):
    ENTITY_NAME = "State"

    @property
    def native_value(self) -> str:
        """Return charging state."""
        try:
            state_value = self._updater.data.get(ATTR_STATE)
            if state_value is None:
                return None
            return CHARGING_STATES.get(state_value, "Unknown")
        except (TypeError, ValueError):
            return None

class EveusSubstateSensor(EveusDiagnosticSensor):
    ENTITY_NAME = "Substate"

    @property
    def native_value(self) -> str:
        """Return substate with context."""
        try:
            state = self._updater.data.get(ATTR_STATE)
            substate = self._updater.data.get(ATTR_SUBSTATE)
            
            if state is None or substate is None:
                return None
                
            if state == 7:  # Error state
                return ERROR_STATES.get(substate, "Unknown Error")
            return NORMAL_SUBSTATES.get(substate, "Unknown State")
        except (TypeError, ValueError):
            return None

class EveusEnabledSensor(EveusDiagnosticSensor):
    ENTITY_NAME = "Enabled"
    _attr_icon = "mdi:power"

    @property
    def native_value(self) -> str:
        """Return if charging is enabled."""
        try:
            value = self._updater.data.get(ATTR_ENABLED)
            if value is None:
                return None
            return "Yes" if value == 1 else "No"
        except (TypeError, ValueError):
            return None

class EveusGroundSensor(EveusDiagnosticSensor):
    ENTITY_NAME = "Ground"
    _attr_icon = "mdi:electric-switch"

    @property
    def native_value(self) -> str:
        """Return ground status."""
        try:
            value = self._updater.data.get(ATTR_GROUND)
            if value is None:
                return None
            return "Connected" if value == 1 else "Not Connected"
        except (TypeError, ValueError):
            return None

class EveusBoxTemperatureSensor(EveusNumericSensor):
    ENTITY_NAME = "Box Temperature"
    _key = ATTR_TEMPERATURE_BOX
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer"
    _attr_suggested_display_precision = 0

class EveusPlugTemperatureSensor(EveusNumericSensor):
    ENTITY_NAME = "Plug Temperature"
    _key = ATTR_TEMPERATURE_PLUG
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer-high"
    _attr_suggested_display_precision = 0

class EveusSystemTimeSensor(BaseEveusEntity, SensorEntity):
    """System time sensor with timezone correction."""

    ENTITY_NAME = "System Time"
    _attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> str:
        """Return timezone-corrected system time."""
        try:
            timestamp = self._updater.data.get(ATTR_SYSTEM_TIME)
            timezone_offset = self._updater.data.get("timeZone", 0)
            
            if timestamp is None:
                return None
                
            # Convert timestamp to datetime and adjust for timezone
            dt = datetime.fromtimestamp(int(timestamp))
            # Subtract timezone offset as it's added by the device
            adjusted_dt = dt - timedelta(hours=timezone_offset)
            return adjusted_dt.strftime("%H:%M")
        except (TypeError, ValueError):
            return None

class EveusSessionTimeSecondsSensor(BaseEveusNumericEntity):
    """Session time in seconds sensor."""

    ENTITY_NAME = "Session Time Seconds"
    _key = ATTR_SESSION_TIME
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer"
    _attr_suggested_display_precision = 0

class EveusSessionTimeSensor(BaseEveusEntity, SensorEntity):
    """Formatted session time sensor."""

    ENTITY_NAME = "Session Time"
    _attr_icon = "mdi:timer"
    _attr_device_class = SensorDeviceClass.DURATION

    @property
    def native_value(self) -> str:
        """Return formatted session time."""
        try:
            seconds = int(self._updater.data.get(ATTR_SESSION_TIME, 0))
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            minutes = (seconds % 3600) // 60

            if days > 0:
                return f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes}m"
            
        except (TypeError, ValueError):
            return "0m"

class EveusCounterAEnergySensor(EveusEnergyBaseSensor):
    ENTITY_NAME = "Counter A Energy"
    _key = ATTR_COUNTER_A_ENERGY
    _attr_icon = "mdi:counter"

class EveusCounterBEnergySensor(EveusEnergyBaseSensor):
    ENTITY_NAME = "Counter B Energy"
    _key = ATTR_COUNTER_B_ENERGY
    _attr_icon = "mdi:counter"

class EveusCounterACostSensor(EveusNumericSensor):
    ENTITY_NAME = "Counter A Cost"
    _key = ATTR_COUNTER_A_COST
    _attr_native_unit_of_measurement = "₴"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:currency-uah"
    _attr_suggested_display_precision = 0

class EveusCounterBCostSensor(EveusNumericSensor):
    ENTITY_NAME = "Counter B Cost"
    _key = ATTR_COUNTER_B_COST
    _attr_native_unit_of_measurement = "₴"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:currency-uah"
    _attr_suggested_display_precision = 0

class EveusBatteryVoltageSensor(EveusNumericSensor):
    ENTITY_NAME = "Battery Voltage"
    _key = ATTR_BATTERY_VOLTAGE
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery"

class EVSocKwhSensor(EveusSensorBase):
    ENTITY_NAME = "SOC Energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:battery-charging"
    _attr_suggested_display_precision = 0
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> float | None:
        """Calculate and return state of charge in kWh."""
        try:
            initial_soc = float(self.hass.states.get("input_number.ev_initial_soc").state)
            max_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
            energy_charged = float(self._updater.data.get("IEM1", 0))
            correction = float(self.hass.states.get("input_number.ev_soc_correction").state)

            if None in (initial_soc, max_capacity, energy_charged, correction):
                return None

            if initial_soc < 0 or initial_soc > 100 or max_capacity <= 0:
                return None

            initial_kwh = (initial_soc / 100) * max_capacity
            efficiency = (1 - correction / 100)
            charged_kwh = energy_charged * efficiency
            total_kwh = initial_kwh + charged_kwh
            
            return round(max(0, min(total_kwh, max_capacity)), 2)
        except (TypeError, ValueError, AttributeError):
            return None

class EVSocPercentSensor(EveusSensorBase):
    ENTITY_NAME = "SOC Percent"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:battery-charging"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    @property
    def native_value(self) -> float | None:
        """Return the state of charge percentage."""
        try:
            soc_kwh = float(self.hass.states.get("sensor.eveus_ev_charger_soc_energy").state)
            max_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
            
            if None in (soc_kwh, max_capacity) or max_capacity <= 0:
                return None

            percentage = round((soc_kwh / max_capacity * 100), 0)
            return max(0, min(percentage, 100))
        except (TypeError, ValueError, AttributeError):
            return None

class TimeToTargetSocSensor(TextEntity, BaseEveusEntity):
    """Time to target SOC text entity."""
    ENTITY_NAME = "Time to Target"
    _attr_icon = "mdi:timer"
    _attr_pattern = None
    _attr_mode = "text"

    @property
    def native_value(self) -> str:
        """Calculate and return formatted time to target."""
        try:
            current_soc = float(self.hass.states.get("sensor.eveus_ev_charger_soc_percent").state)
            target_soc = float(self.hass.states.get("input_number.ev_target_soc").state)
            power_meas = float(self._updater.data.get(ATTR_POWER, 0))
            battery_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
            correction = float(self.hass.states.get("input_number.ev_soc_correction").state)

            if None in (current_soc, target_soc, power_meas, battery_capacity, correction):
                return "-"

            remaining_kwh = (target_soc - current_soc) * battery_capacity / 100
            if remaining_kwh <= 0:
                return "-"
                
            efficiency = (1 - correction / 100)
            power_kw = power_meas * efficiency / 1000
            
            if power_kw <= 0:
                return "-"

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
            return "-"

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eveus sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    updater = data["updater"]

    sensors = [
        EveusVoltageSensor(updater),
        EveusCurrentSensor(updater),
        EveusPowerSensor(updater),
        EveusCurrentSetSensor(updater),
        EveusSessionEnergySensor(updater),
        EveusTotalEnergySensor(updater),
        EveusStateSensor(updater),
        EveusSubstateSensor(updater),
        EveusEnabledSensor(updater),
        EveusGroundSensor(updater),
        EveusBoxTemperatureSensor(updater),
        EveusPlugTemperatureSensor(updater),
        EveusBatteryVoltageSensor(updater),
        EveusSessionTimeSensor(updater),
        EveusSessionTimeSecondsSensor(updater),
        EveusSystemTimeSensor(updater),
        EveusConnectionErrorsSensor(updater),
        EveusCounterAEnergySensor(updater),
        EveusCounterBEnergySensor(updater),
        EveusCounterACostSensor(updater),
        EveusCounterBCostSensor(updater),
        EVSocKwhSensor(updater),
        EVSocPercentSensor(updater),
        TimeToTargetSocSensor(updater),
    ]

    if "entities" not in data:
        data["entities"] = {}

    data["entities"]["sensor"] = {
        sensor.unique_id: sensor for sensor in sensors
    }

    async_add_entities(sensors)
