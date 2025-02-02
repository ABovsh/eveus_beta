"""Support for Eveus sensors."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

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
    pass

class EveusNumericSensor(EveusSensorBase, BaseEveusNumericEntity):
    """Base class for numeric sensors."""
    pass

class EveusDiagnosticSensor(EveusSensorBase):
    """Base class for diagnostic sensors."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information"

class EveusEnergyBaseSensor(EveusNumericSensor):
    """Base energy sensor with improved precision."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1

# Regular Sensors
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

# State Sensors
class EveusStateSensor(EveusDiagnosticSensor):
    ENTITY_NAME = "State"

    @property
    def native_value(self) -> str:
        """Return charging state."""
        try:
            return CHARGING_STATES.get(self._updater.data.get(ATTR_STATE, -1), "Unknown")
        except (TypeError, ValueError):
            return "Unknown"

class EveusSubstateSensor(EveusDiagnosticSensor):
    ENTITY_NAME = "Substate"

    @property
    def native_value(self) -> str:
        """Return substate with context."""
        try:
            state = self._updater.data.get(ATTR_STATE)
            substate = self._updater.data.get(ATTR_SUBSTATE)
            
            if state == 7:  # Error state
                return ERROR_STATES.get(substate, "Unknown Error")
            return NORMAL_SUBSTATES.get(substate, "Unknown State")
        except (TypeError, ValueError):
            return "Unknown"

class EveusEnabledSensor(EveusDiagnosticSensor):
    ENTITY_NAME = "Enabled"
    _attr_icon = "mdi:power"

    @property
    def native_value(self) -> str:
        """Return if charging is enabled."""
        try:
            return "Yes" if self._updater.data.get(ATTR_ENABLED) == 1 else "No"
        except (TypeError, ValueError):
            return "Unknown"

class EveusGroundSensor(EveusDiagnosticSensor):
    ENTITY_NAME = "Ground"
    _attr_icon = "mdi:electric-switch"

    @property
    def native_value(self) -> str:
        """Return ground status."""
        try:
            return "Connected" if self._updater.data.get(ATTR_GROUND) == 1 else "Not Connected"
        except (TypeError, ValueError):
            return "Unknown"

# Temperature Sensors
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

# System Time and Duration Sensors
class EveusSystemTimeSensor(EveusSensorBase):
    ENTITY_NAME = "System Time"
    _attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> str:
        """Return formatted system time."""
        try:
            timestamp = int(self._updater.data.get(ATTR_SYSTEM_TIME, 0))
            return datetime.fromtimestamp(timestamp).strftime("%H:%M")
        except (TypeError, ValueError):
            return "unknown"

class EveusSessionTimeSensor(EveusNumericSensor):
    ENTITY_NAME = "Session Time"
    _key = ATTR_SESSION_TIME
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer"
    _attr_suggested_display_precision = 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes
        try:
            seconds = int(self.native_value)
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            minutes = (seconds % 3600) // 60

            if days > 0:
                formatted_time = f"{days}d {hours:02d}h {minutes:02d}m"
            elif hours > 0:
                formatted_time = f"{hours}h {minutes:02d}m"
            else:
                formatted_time = f"{minutes}m"
            
            attrs["formatted_time"] = formatted_time
            
        except (TypeError, ValueError):
            attrs["formatted_time"] = "0m"
            
        return attrs

# Counter Sensors
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

# SOC Sensors
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
            
            if soc_kwh >= 0 and max_capacity > 0:
                percentage = round((soc_kwh / max_capacity * 100), 0)
                return max(0, min(percentage, 100))
            return None
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
            current_soc = float(self.hass.states.get("sensor.eveus_ev_charger_soc_percent").state

    @property
    def native_value(self) -> str:
        """Calculate and return formatted time to target."""
        try:
            current_soc = float(self.hass.states.get("sensor.eveus_ev_charger_soc_percent").state)
            target_soc = float(self.hass.states.get("input_number.ev_target_soc").state)
            power_meas = float(self._updater.data.get(ATTR_POWER, 0))
            battery_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
            correction = float(self.hass.states.get("input_number.ev_soc_correction").state)

            remaining_kwh = (target_soc - current_soc) * battery_capacity / 100
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
    updater = EveusUpdater(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        hass=hass,
    )

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
        EveusSystemTimeSensor(updater),
        EveusSessionTimeSensor(updater),
        EveusCounterAEnergySensor(updater),
        EveusCounterBEnergySensor(updater),
        EveusCounterACostSensor(updater),
        EveusCounterBCostSensor(updater),
        EVSocKwhSensor(updater),
        EVSocPercentSensor(updater),
        TimeToTargetSocSensor(updater),
    ]

    if "entities" not in hass.data[DOMAIN][entry.entry_id]:
        hass.data[DOMAIN][entry.entry_id]["entities"] = {}

    hass.data[DOMAIN][entry.entry_id]["entities"]["sensor"] = {
        sensor.unique_id: sensor for sensor in sensors
    }

    async_add_entities(sensors)
