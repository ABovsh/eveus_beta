"""Support for Eveus sensors."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Final

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity
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
    PERCENTAGE,
)
from homeassistant.util import dt as dt_util

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
    HELPER_EV_BATTERY_CAPACITY,
    HELPER_EV_INITIAL_SOC,
    HELPER_EV_SOC_CORRECTION,
    HELPER_EV_TARGET_SOC,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

class BaseEveusSensor(SensorEntity, RestoreEntity):
    """Base sensor implementation."""

    _attr_has_entity_name: Final = True
    _attr_should_poll = True
    _attr_entity_registry_enabled_default: Final = True
    _attr_entity_registry_visible_default: Final = True
    _update_interval = UPDATE_INTERVAL
    _translation_prefix = "sensor"

    def __init__(self, session_manager, name: str) -> None:
        """Initialize the sensor."""
        self._session_manager = session_manager
        self._attr_name = name
        self._attr_unique_id = f"{session_manager._host}_{name}"
        self._attr_translation_key = f"{self._translation_prefix}_{name.lower().replace(' ', '_')}"
        self._previous_value = None
        self._restored = False

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        if state := await self.async_get_last_state():
            if state.state not in ('unknown', 'unavailable'):
                try:
                    if hasattr(self, '_attr_suggested_display_precision'):
                        self._previous_value = float(state.state)
                    else:
                        self._previous_value = state.state
                    self._restored = True
                except (TypeError, ValueError):
                    self._previous_value = state.state

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._session_manager._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._session_manager._host})",
            "configuration_url": f"http://{self._session_manager._host}",
            "suggested_area": "Garage",
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {
            "last_update": dt_util.as_local(
                self._session_manager.last_successful_connection
            ).isoformat() if self._session_manager.last_successful_connection else None,
            "host": self._session_manager._host,
            "restored": self._restored,
        }
        if self._previous_value is not None:
            attrs["previous_value"] = self._previous_value
        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._session_manager.available

    async def async_update(self) -> None:
        """Update the sensor."""
        try:
            state = await self._session_manager.get_state()
            self._handle_state_update(state)
        except Exception as err:
            _LOGGER.error(
                "Error updating sensor %s: %s",
                self.name,
                str(err),
                exc_info=True
            )

    def _handle_state_update(self, state: dict) -> None:
        """Handle state update from device."""
        raise NotImplementedError

class BaseNumericSensor(BaseEveusSensor):
    """Base numeric sensor with validation."""

    _attr_suggested_display_precision: Final = 1
    _attribute: str = None
    _min_value: float = float('-inf')
    _max_value: float = float('inf')
    _warning_threshold: float | None = None
    _critical_threshold: float | None = None

    def _handle_state_update(self, state: dict) -> None:
        """Update numeric sensor state."""
        try:
            value = state.get(self._attribute)
            if value is None:
                if not self._restored:
                    self._attr_native_value = None
                return

            value = float(value)
            if not self._validate_value(value):
                return

            self._attr_native_value = round(value, self._attr_suggested_display_precision)
            self._previous_value = self._attr_native_value
            self._restored = False

            self._check_thresholds(value)

        except (TypeError, ValueError) as err:
            _LOGGER.error(
                "Error converting value for %s: %s",
                self.name,
                str(err)
            )

    def _validate_value(self, value: float) -> bool:
        """Validate value is within defined range."""
        if not self._min_value <= value <= self._max_value:
            _LOGGER.warning(
                "%s value out of range [%f, %f]: %f",
                self.name,
                self._min_value,
                self._max_value,
                value
            )
            return False
        return True

    def _check_thresholds(self, value: float) -> None:
        """Check warning and critical thresholds."""
        if self._critical_threshold is not None and value >= self._critical_threshold:
            _LOGGER.warning(
                "%s value critically high: %f",
                self.name,
                value
            )
        elif self._warning_threshold is not None and value >= self._warning_threshold:
            _LOGGER.warning(
                "%s value high: %f",
                self.name,
                value
            )

class EveusVoltageSensor(BaseNumericSensor):
    """Voltage sensor implementation."""
    
    _attribute = ATTR_VOLTAGE
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _min_value = 180
    _max_value = 260
    _warning_threshold = 245
    _critical_threshold = 255

class EveusCurrentSensor(BaseNumericSensor):
    """Current sensor implementation."""
    
    _attribute = ATTR_CURRENT
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _min_value = 0
    _max_value = 32
    _warning_threshold = 30
    _critical_threshold = 32

class EveusPowerSensor(BaseNumericSensor):
    """Power sensor implementation."""

    _attribute = ATTR_POWER
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _min_value = 0
    _max_value = 7400  # 32A * 230V
    _warning_threshold = 7000
    _critical_threshold = 7400

    def _validate_value(self, value: float) -> bool:
        """Validate power with voltage consideration."""
        try:
            voltage = float(self._session_manager.last_state.get(ATTR_VOLTAGE, 230))
            max_power = voltage * 32 * 1.1  # 10% margin
            if not 0 <= value <= max_power:
                _LOGGER.warning("Power out of expected range: %f W", value)
                return False
            return True
        except (TypeError, ValueError, AttributeError):
            return super()._validate_value(value)

class EveusSessionEnergySensor(BaseNumericSensor):
    """Session energy sensor implementation."""

    _attribute = ATTR_SESSION_ENERGY
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1
    _min_value = 0

    def _validate_value(self, value: float) -> bool:
        """Validate session energy."""
        if value < 0:
            _LOGGER.warning("Negative session energy value: %f kWh", value)
            return False
        return True

class EveusTotalEnergySensor(BaseNumericSensor):
    """Total energy sensor implementation."""

    _attribute = ATTR_TOTAL_ENERGY
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1
    _min_value = 0

class EveusCurrentSetSensor(BaseNumericSensor):
    """Current set sensor implementation."""

    _attribute = ATTR_CURRENT_SET
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _min_value = 6
    _max_value = 32

class EveusBoxTemperatureSensor(BaseNumericSensor):
    """Box temperature sensor implementation."""

    _attribute = ATTR_TEMPERATURE_BOX
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _min_value = -20
    _max_value = 100
    _warning_threshold = 60
    _critical_threshold = 80

class EveusPlugTemperatureSensor(BaseNumericSensor):
    """Plug temperature sensor implementation."""

    _attribute = ATTR_TEMPERATURE_PLUG
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _min_value = -20
    _max_value = 100
    _warning_threshold = 50
    _critical_threshold = 65

class EveusBatteryVoltageSensor(BaseNumericSensor):
    """Battery voltage sensor implementation."""

    _attribute = ATTR_BATTERY_VOLTAGE
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _min_value = 2.0
    _max_value = 3.3

    def _validate_value(self, value: float) -> bool:
        """Validate battery voltage with warning levels."""
        if value < 2.5:
            _LOGGER.warning("Battery voltage critically low: %f V", value)
        elif value < 2.7:
            _LOGGER.warning("Battery voltage low: %f V", value)
        return self._min_value <= value <= self._max_value

class EveusSystemTimeSensor(BaseEveusSensor):
    """System time sensor implementation."""

    _attribute = ATTR_SYSTEM_TIME
    _attr_native_unit_of_measurement = "HH:mm"

    def _handle_state_update(self, state: dict) -> None:
        """Handle system time update."""
        try:
            timestamp = int(state.get(self._attribute, 0))
            if timestamp == 0:
                raise ValueError("Invalid timestamp")

            # Convert timestamp to datetime in local timezone
            local_time = datetime.fromtimestamp(timestamp)
            formatted_time = local_time.strftime("%H:%M")
            
            self._attr_native_value = formatted_time
            self._attr_extra_state_attributes = {
                **self.extra_state_attributes,
                "timestamp": timestamp,
                "full_datetime": local_time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
        except (TypeError, ValueError, OSError) as err:
            _LOGGER.error("Error processing system time: %s", str(err))
            self._attr_native_value = None

class EveusSessionTimeSensor(BaseEveusSensor):
    """Session time sensor implementation."""

    _attribute = ATTR_SESSION_TIME
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def _handle_state_update(self, state: dict) -> None:
        """Handle session time update."""
        try:
            seconds = int(state.get(self._attribute, 0))
            if seconds < 0:
                _LOGGER.warning("Negative session time: %d seconds", seconds)
                return
                
            self._attr_native_value = seconds

            # Calculate formatted time
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            minutes = (seconds % 3600) // 60

            if days > 0:
                formatted_time = f"{days}d {hours:02d}h {minutes:02d}m"
            elif hours > 0:
                formatted_time = f"{hours}h {minutes:02d}m"
            else:
                formatted_time = f"{minutes}m"

            self._attr_extra_state_attributes = {
                **self.extra_state_attributes,
                "formatted_time": formatted_time,
                "days": days,
                "hours": hours,
                "minutes": minutes,
            }

        except (TypeError, ValueError) as err:
            _LOGGER.error("Error processing session time: %s", str(err))
            self._attr_native_value = 0

class EveusStateSensor(BaseEveusSensor):
    """Charging state sensor implementation."""

    _attribute = ATTR_STATE
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def _handle_state_update(self, state: dict) -> None:
        """Handle charging state update."""
        try:
            state_code = int(state.get(self._attribute, -1))
            if state_code not in CHARGING_STATES:
                _LOGGER.warning("Unknown charging state code: %d", state_code)
                self._attr_native_value = "Unknown"
                return
            
            self._attr_native_value = CHARGING_STATES[state_code]
            self._attr_extra_state_attributes = {
                **self.extra_state_attributes,
                "state_code": state_code,
                "is_charging": state_code == 4,
                "has_error": state_code == 7,
            }

        except (TypeError, ValueError) as err:
            _LOGGER.error("Error processing charging state: %s", str(err))
            self._attr_native_value = "Error"

class EveusSubstateSensor(BaseEveusSensor):
    """Substate sensor implementation."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def _handle_state_update(self, state: dict) -> None:
        """Handle substate update with enhanced error detection."""
        try:
            state_code = int(state.get(ATTR_STATE, -1))
            substate_code = int(state.get(ATTR_SUBSTATE, -1))

            if state_code == 7:  # Error state
                if substate_code not in ERROR_STATES:
                    _LOGGER.warning("Unknown error state: %d", substate_code)
                    self._attr_native_value = "Unknown Error"
                else:
                    self._attr_native_value = ERROR_STATES[substate_code]
                    if substate_code > 0:  # Any non-zero error state
                        _LOGGER.error("Charger error detected: %s", self._attr_native_value)
            else:
                if substate_code not in NORMAL_SUBSTATES:
                    _LOGGER.warning("Unknown substate: %d", substate_code)
                    self._attr_native_value = "Unknown State"
                else:
                    self._attr_native_value = NORMAL_SUBSTATES[substate_code]

            self._attr_extra_state_attributes = {
                **self.extra_state_attributes,
                "state_code": state_code,
                "substate_code": substate_code,
                "is_error": state_code == 7,
                "requires_attention": substate_code > 0 and state_code == 7,
            }

        except (TypeError, ValueError) as err:
            _LOGGER.error("Error processing substate: %s", str(err))
            self._attr_native_value = "Error"

class EveusEnabledSensor(BaseEveusSensor):
    """Enabled state sensor implementation."""

    _attribute = ATTR_ENABLED
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["Yes", "No", "Unknown"]

    def _handle_state_update(self, state: dict) -> None:
        """Handle enabled state update."""
        try:
            value = state.get(self._attribute)
            if value is None:
                self._attr_native_value = "Unknown"
            else:
                self._attr_native_value = "Yes" if int(value) == 1 else "No"
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error processing enabled state: %s", str(err))
            self._attr_native_value = "Unknown"

class EveusGroundSensor(BaseEveusSensor):
    """Ground connection sensor implementation."""

    _attribute = ATTR_GROUND
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["Connected", "Not Connected", "Unknown"]

    def _handle_state_update(self, state: dict) -> None:
        """Handle ground status update."""
        try:
            value = state.get(self._attribute)
            if value is None:
                self._attr_native_value = "Unknown"
            else:
                self._attr_native_value = "Connected" if int(value) == 1 else "Not Connected"
                if int(value) != 1:
                    _LOGGER.warning("Ground connection issue detected")
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error processing ground state: %s", str(err))
            self._attr_native_value = "Unknown"

class EveusCounterAEnergySensor(BaseNumericSensor):
    """Counter A energy sensor implementation."""

    _attribute = ATTR_COUNTER_A_ENERGY
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1
    _min_value = 0

    def _validate_value(self, value: float) -> bool:
        """Validate energy counter value."""
        if value < 0:
            _LOGGER.warning("Negative energy counter A value: %f kWh", value)
            return False
        
        # Check for unrealistic jumps
        if (self._previous_value is not None and 
            abs(value - self._previous_value) > 10):  # 10 kWh jump threshold
            _LOGGER.warning(
                "Large energy counter A value jump detected: %f -> %f kWh",
                self._previous_value,
                value
            )
        return True

class EveusCounterBEnergySensor(BaseNumericSensor):
    """Counter B energy sensor implementation."""

    _attribute = ATTR_COUNTER_B_ENERGY
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1
    _min_value = 0

    def _validate_value(self, value: float) -> bool:
        """Validate energy counter value."""
        if value < 0:
            _LOGGER.warning("Negative energy counter B value: %f kWh", value)
            return False
        
        # Check for unrealistic jumps
        if (self._previous_value is not None and 
            abs(value - self._previous_value) > 10):  # 10 kWh jump threshold
            _LOGGER.warning(
                "Large energy counter B value jump detected: %f -> %f kWh",
                self._previous_value,
                value
            )
        return True

class EveusCounterACostSensor(BaseNumericSensor):
    """Counter A cost sensor implementation."""

    _attribute = ATTR_COUNTER_A_COST
    _attr_native_unit_of_measurement = "₴"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1
    _min_value = 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes
        if self._attr_native_value is not None:
            try:
                energy = self.hass.states.get(
                    f"sensor.{self._session_manager._host}_counter_a_energy"
                )
                if energy and energy.state not in ('unknown', 'unavailable'):
                    attrs["rate"] = round(
                        self._attr_native_value / float(energy.state), 
                        2
                    )
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        return attrs

class EveusCounterBCostSensor(BaseNumericSensor):
    """Counter B cost sensor implementation."""

    _attribute = ATTR_COUNTER_B_COST
    _attr_native_unit_of_measurement = "₴"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1
    _min_value = 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes
        if self._attr_native_value is not None:
            try:
                energy = self.hass.states.get(
                    f"sensor.{self._session_manager._host}_counter_b_energy"
                )
                if energy and energy.state not in ('unknown', 'unavailable'):
                    attrs["rate"] = round(
                        self._attr_native_value / float(energy.state), 
                        2
                    )
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        return attrs

class EVSocKwhSensor(BaseEveusSensor):
    """EV State of Charge energy sensor implementation."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 1

    def _handle_state_update(self, state: dict) -> None:
        """Calculate and update SOC in kWh."""
        try:
            initial_soc = float(self.hass.states.get(HELPER_EV_INITIAL_SOC).state)
            max_capacity = float(self.hass.states.get(HELPER_EV_BATTERY_CAPACITY).state)
            energy_charged = float(state.get(ATTR_COUNTER_A_ENERGY, 0))
            correction = float(self.hass.states.get(HELPER_EV_SOC_CORRECTION).state)

            # Validate inputs
            if not (0 <= initial_soc <= 100 and max_capacity > 0 and 0 <= correction <= 10):
                _LOGGER.error("Invalid input parameters for SOC calculation")
                return

            initial_kwh = (initial_soc / 100) * max_capacity
            efficiency = (1 - correction / 100)
            charged_kwh = energy_charged * efficiency
            total_kwh = initial_kwh + charged_kwh

            # Ensure result is within valid range
            self._attr_native_value = max(0, min(total_kwh, max_capacity))

            # Store calculation details in attributes
            self._attr_extra_state_attributes = {
                **self.extra_state_attributes,
                "initial_soc_kwh": round(initial_kwh, 2),
                "energy_charged": round(energy_charged, 2),
                "efficiency": round(efficiency, 3),
                "charging_losses": round(energy_charged * (correction / 100), 2),
                "max_capacity": max_capacity,
            }

        except (TypeError, ValueError, AttributeError) as err:
            _LOGGER.error("Error calculating SOC: %s", str(err))
            if self._restored:
                _LOGGER.info("Keeping restored value: %s", self._attr_native_value)
            else:
                self._attr_native_value = None
                
class EVSocPercentSensor(BaseEveusSensor):
    """EV State of Charge percentage sensor implementation."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def _get_helper_value(self, entity_id: str) -> float:
        """Get and validate helper value."""
        state = self.hass.states.get(entity_id)
        if not state or state.state in ('unknown', 'unavailable'):
            raise ValueError(f"Helper {entity_id} unavailable")
        return float(state.state)

    def _handle_state_update(self, state: dict) -> None:
        """Calculate and update SOC percentage."""
        try:
            # Get and validate all required values
            max_capacity = self._get_helper_value(HELPER_EV_BATTERY_CAPACITY)
            initial_soc = self._get_helper_value(HELPER_EV_INITIAL_SOC)
            correction = self._get_helper_value(HELPER_EV_SOC_CORRECTION)
            energy_charged = float(state.get(ATTR_COUNTER_A_ENERGY, 0))

            # Validate ranges
            if not (0 <= initial_soc <= 100 and max_capacity > 0 and 0 <= correction <= 10):
                raise ValueError("Helper values out of valid range")

            # Calculate SOC
            efficiency = (1 - correction / 100)
            energy_added = energy_charged * efficiency
            initial_energy = (initial_soc / 100) * max_capacity
            total_energy = initial_energy + energy_added
            percentage = (total_energy / max_capacity) * 100

            # Set valid value
            self._attr_native_value = max(0, min(round(percentage), 100))

            # Update attributes
            self._attr_extra_state_attributes = {
                **self.extra_state_attributes,
                "initial_soc": initial_soc,
                "energy_charged": round(energy_charged, 2),
                "energy_added": round(energy_added, 2),
                "efficiency": round(efficiency * 100, 1),
                "max_capacity": max_capacity,
                "current_energy": round(total_energy, 2),
                "available_capacity": round(max_capacity - total_energy, 2)
            }

        except Exception as err:
            _LOGGER.error(
                "Error calculating SOC percentage for %s: %s",
                self.name,
                str(err)
            )
            if not self._restored:
                self._attr_native_value = None

class TimeToTargetSocSensor(BaseEveusSensor):
    """Time to target SOC sensor implementation."""

    def _handle_state_update(self, state: dict) -> None:
        """Calculate and update time to target SOC."""
        try:
            # Check if charging
            state_code = int(state.get(ATTR_STATE, -1))
            if state_code != 4:  # Not charging
                charging_state = CHARGING_STATES.get(state_code, "Unknown")
                self._attr_native_value = f"Not charging ({charging_state})"
                self._attr_extra_state_attributes = {
                    **self.extra_state_attributes,
                    "state": charging_state,
                    "charging_active": False,
                }
                return

            # Get current and target values
            soc_state = self.hass.states.get(f"sensor.{self._session_manager._host}_soc_percent")
            if not soc_state or soc_state.state in ('unknown', 'unavailable'):
                self._attr_native_value = "Unknown SOC state"
                return

            current_soc = float(soc_state.state)
            target_soc = float(self.hass.states.get(HELPER_EV_TARGET_SOC).state)

            if current_soc >= target_soc:
                self._attr_native_value = "Target reached"
                self._attr_extra_state_attributes = {
                    **self.extra_state_attributes,
                    "target_reached": True,
                    "current_soc": current_soc,
                    "target_soc": target_soc,
                }
                return

            power_meas = float(state.get(ATTR_POWER, 0))
            if power_meas < 100:  # Minimum power threshold
                self._attr_native_value = f"Insufficient power ({power_meas:.0f}W)"
                self._attr_extra_state_attributes = {
                    **self.extra_state_attributes,
                    "power_too_low": True,
                    "current_power": power_meas,
                }
                return

            # Calculate remaining time
            battery_capacity = float(self.hass.states.get(HELPER_EV_BATTERY_CAPACITY).state)
            correction = float(self.hass.states.get(HELPER_EV_SOC_CORRECTION).state)

            remaining_kwh = (target_soc - current_soc) * battery_capacity / 100
            efficiency = (1 - correction / 100)
            power_kw = power_meas * efficiency / 1000
            total_minutes = round(remaining_kwh / power_kw * 60)

            # Format time string
            if total_minutes < 1:
                self._attr_native_value = "Less than 1m"
            else:
                days = int(total_minutes // 1440)
                hours = int((total_minutes % 1440) // 60)
                minutes = int(total_minutes % 60)

                if days > 0:
                    self._attr_native_value = f"{days}d {hours}h {minutes}m"
                elif hours > 0:
                    self._attr_native_value = f"{hours}h {minutes}m"
                else:
                    self._attr_native_value = f"{minutes}m"

            # Store calculation details in attributes
            self._attr_extra_state_attributes = {
                **self.extra_state_attributes,
                "current_soc": current_soc,
                "target_soc": target_soc,
                "charging_power": power_meas,
                "efficiency": efficiency,
                "remaining_kwh": round(remaining_kwh, 2),
                "estimated_minutes": total_minutes,
                "charging_active": True,
                "power_sufficient": True,
            }

        except (TypeError, ValueError, AttributeError) as err:
            _LOGGER.error("Error calculating time to target: %s", str(err))
            self._attr_native_value = "Calculation error"
            self._attr_extra_state_attributes = {
                **self.extra_state_attributes,
                "error": str(err),
                "charging_active": False,
            }

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus sensors."""
    session_manager = hass.data[DOMAIN][entry.entry_id]["session_manager"]

    sensors = [
        EveusVoltageSensor(session_manager, "Voltage"),
        EveusCurrentSensor(session_manager, "Current"),
        EveusPowerSensor(session_manager, "Power"),
        EveusCurrentSetSensor(session_manager, "Current Set"),
        EveusSessionEnergySensor(session_manager, "Session Energy"),
        EveusTotalEnergySensor(session_manager, "Total Energy"),
        EveusStateSensor(session_manager, "State"),
        EveusSubstateSensor(session_manager, "Substate"),
        EveusEnabledSensor(session_manager, "Enabled"),
        EveusGroundSensor(session_manager, "Ground"),
        EveusBoxTemperatureSensor(session_manager, "Box Temperature"),
        EveusPlugTemperatureSensor(session_manager, "Plug Temperature"),
        EveusBatteryVoltageSensor(session_manager, "Battery Voltage"),
        EveusSystemTimeSensor(session_manager, "System Time"),
        EveusSessionTimeSensor(session_manager, "Session Time"),
        EveusCounterAEnergySensor(session_manager, "Counter A Energy"),
        EveusCounterBEnergySensor(session_manager, "Counter B Energy"),
        EveusCounterACostSensor(session_manager, "Counter A Cost"),
        EveusCounterBCostSensor(session_manager, "Counter B Cost"),
        EVSocKwhSensor(session_manager, "SOC Energy"),
        EVSocPercentSensor(session_manager, "SOC Percent"),
        TimeToTargetSocSensor(session_manager, "Time to Target"),
    ]

    # Store entity references
    hass.data[DOMAIN][entry.entry_id]["entities"]["sensor"] = {
        sensor.unique_id: sensor for sensor in sensors
    }

    async_add_entities(sensors)
