"""Support for Eveus sensors."""
from __future__ import annotations

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any

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
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
)

from .const import (
    DOMAIN,
    SCAN_INTERVAL,
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

from .mixins import (
    SessionMixin,
    DeviceInfoMixin,
    ErrorHandlingMixin,
    UpdaterMixin,
    StateMixin,
    ValidationMixin
)

_LOGGER = logging.getLogger(__name__)

class EveusUpdater(SessionMixin, ErrorHandlingMixin, UpdaterMixin):
    """Handle Eveus data updates."""

    def __init__(self, host: str, username: str, password: str, hass: HomeAssistant) -> None:
        """Initialize updater."""
        super().__init__()
        self.initialize(host, username, password, hass)
        self._sensors = []
        self._update_task = None
        self._available = True
        self._last_update = datetime.now().timestamp()
        self._update_lock = asyncio.Lock()
        self._min_update_interval = 5
        self._request_timeout = 10
        self._data = {}

    def register_sensor(self, sensor: "BaseEveusSensor") -> None:
        """Register a sensor for updates."""
        if sensor not in self._sensors:
            self._sensors.append(sensor)

    async def async_start_updates(self) -> None:
        """Start the update loop."""
        try:
            async with asyncio.timeout(self._request_timeout):
                await self.async_update()
        except asyncio.TimeoutError:
            _LOGGER.warning("Initial update timed out")
            self._available = False
        except Exception as err:
            _LOGGER.error("Error during initial update: %s", str(err))
            self._available = False

    async def async_update(self) -> None:
        """Update data from device with rate limiting."""
        async with self._update_lock:
            current_time = datetime.now().timestamp()
            if current_time - self._last_update < self._min_update_interval:
                return

            try:
                data = await self.async_api_call("main")
                if data and isinstance(data, dict):
                    self._data = data
                    self._available = True
                    self._last_update = current_time
                    self._error_count = 0

                    for sensor in self._sensors:
                        try:
                            if hasattr(sensor, "async_write_ha_state"):
                                sensor.async_write_ha_state()
                        except Exception as err:
                            _LOGGER.error("Error updating sensor %s: %s", 
                                getattr(sensor, 'name', 'unknown'), str(err))
                else:
                    _LOGGER.warning("Invalid or empty API response")
                    self._available = False

            except Exception as err:
                self._error_count += 1
                self._available = self._error_count < self._max_errors
                _LOGGER.error("Update failed: %s", str(err))

class BaseEveusSensor(DeviceInfoMixin, StateMixin, ValidationMixin, SensorEntity, RestoreEntity):
    """Base implementation for Eveus sensors."""
    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__()
        self._updater = updater
        self._updater.register_sensor(self)
        self._previous_value = None
        self._attr_has_entity_name = True
        self._attr_should_poll = False
        self._attr_entity_registry_enabled_default = True
        self._attr_entity_registry_visible_default = True

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Restore previous state if available
        if state := await self.async_get_last_state():
            if state.state not in ('unknown', 'unavailable'):
                try:
                    if hasattr(self, '_attr_suggested_display_precision'):
                        self._previous_value = float(state.state)
                    else:
                        self._previous_value = state.state
                except (TypeError, ValueError):
                    self._previous_value = state.state

        # Start the updater
        await self._updater.async_start_updates()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._updater.available

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {
            "last_update": datetime.fromtimestamp(self._updater.last_update).isoformat(),
            "host": self._updater._host,
        }
        if self._previous_value is not None:
            attrs["previous_value"] = self._previous_value
        return attrs

class NumericSensor(BaseEveusSensor):
    """Base class for numeric sensors."""
    
    def __init__(self, updater: EveusUpdater, name: str, key: str, 
                unit: str = None, device_class: str = None,
                icon: str = None, precision: int = None) -> None:
        """Initialize numeric sensor."""
        super().__init__(updater)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{updater._host}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_icon = icon
        self._attr_suggested_display_precision = precision
        self._attr_state_class = SensorStateClass.MEASUREMENT
        _LOGGER.debug("Initialized sensor %s with key %s", name, key)

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        try:
            value = self._updater.get_data_value(self._key)
            _LOGGER.debug("Sensor %s (%s) raw value: %s", self.name, self._key, value)
            
            if value is None:
                return None
                
            # Convert to float for numeric sensors
            try:
                float_value = float(value)
                _LOGGER.debug("Sensor %s converted value: %s", self.name, float_value)
                return float_value
            except (ValueError, TypeError):
                _LOGGER.warning("Could not convert value %s for sensor %s", value, self.name)
                return None
                
        except Exception as err:
            _LOGGER.error("Error getting value for sensor %s: %s", self.name, str(err))
            return None

class EnergySensor(NumericSensor):
    """Energy sensor implementation."""
    def __init__(self, updater: EveusUpdater, name: str, key: str):
        """Initialize energy sensor."""
        super().__init__(
            updater=updater,
            name=name,
            key=key,
            unit=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            precision=1
        )
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

class StateSensor(BaseEveusSensor):
    """State sensor implementation."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    
    def __init__(self, updater: EveusUpdater, name: str, key: str,
                state_map: dict, icon: str = "mdi:information"):
        """Initialize state sensor."""
        super().__init__(updater)
        self._attr_name = name
        self._attr_unique_id = f"{updater._host}_{key}"
        self._key = key
        self._state_map = state_map
        self._attr_icon = icon

    @property
    def native_value(self) -> str:
        """Return mapped state value."""
        return self.get_mapped_state(
            self._updater.get_data_value(self._key),
            self._state_map
        )

class EveusGroundSensor(BaseEveusSensor):
    """Ground connection sensor."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:power-plug"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize ground sensor."""
        super().__init__(updater)
        self._attr_name = "Ground Connection"
        self._attr_unique_id = f"{updater._host}_ground"

    @property
    def native_value(self) -> str:
        """Return ground status."""
        return "Connected" if self._updater.get_data_value(ATTR_GROUND) == 1 else "Not Connected"

class EVSocKwhSensor(BaseEveusSensor):
    """EV State of Charge energy sensor."""
    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize SOC energy sensor."""
        super().__init__(updater)
        self._attr_name = "SOC Energy"
        self._attr_unique_id = f"{updater._host}_soc_kwh"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_icon = "mdi:battery-charging"
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Calculate and return state of charge in kWh."""
        try:
            initial_soc = float(self.hass.states.get("input_number.ev_initial_soc").state)
            max_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
            energy_charged = self._updater.get_data_value("IEM1", 0)
            correction = float(self.hass.states.get("input_number.ev_soc_correction").state)

            if not self.validate_numeric_value(initial_soc, 0, 100):
                return None
            if not self.validate_numeric_value(max_capacity, 0, float('inf')):
                return None

            initial_kwh = (initial_soc / 100) * max_capacity
            efficiency = (1 - correction / 100)
            charged_kwh = energy_charged * efficiency
            total_kwh = initial_kwh + charged_kwh
            
            return round(max(0, min(total_kwh, max_capacity)), 2)
            
        except (TypeError, ValueError, AttributeError):
            return None

class EVSocPercentSensor(BaseEveusSensor):
    """EV State of Charge percentage sensor."""
    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize SOC percentage sensor."""
        super().__init__(updater)
        self._attr_name = "SOC Percent"
        self._attr_unique_id = f"{updater._host}_soc_percent"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_native_unit_of_measurement = "%"
        self._attr_icon = "mdi:battery-charging"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_display_precision = 0

    @property
    def native_value(self) -> float | None:
        """Return state of charge percentage."""
        try:
            soc_kwh = float(self.hass.states.get("sensor.eveus_ev_charger_soc_energy").state)
            max_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
            
            if not self.validate_numeric_value(soc_kwh, 0, float('inf')) or \
               not self.validate_numeric_value(max_capacity, 0, float('inf')):
                return None
                
            percentage = round((soc_kwh / max_capacity * 100), 0)
            return max(0, min(percentage, 100))
            
        except (TypeError, ValueError, AttributeError):
            return None

class TimeToTargetSocSensor(BaseEveusSensor):
    """Time to target SOC sensor."""
    _attr_icon = "mdi:timer"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize time to target sensor."""
        super().__init__(updater)
        self._attr_name = "Time to Target"
        self._attr_unique_id = f"{updater._host}_time_to_target"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str:
        """Calculate and return time to target."""
        try:
            if self._updater.get_data_value(ATTR_STATE) != 4:
                return "Not charging"

            current_soc = float(self.hass.states.get("sensor.eveus_ev_charger_soc_percent").state)
            target_soc = float(self.hass.states.get("input_number.ev_target_soc").state)
            power_meas = self._updater.get_data_value(ATTR_POWER, 0)
            battery_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
            correction = float(self.hass.states.get("input_number.ev_soc_correction").state)

            if not all(self.validate_numeric_value(x, 0, float('inf')) 
                      for x in [current_soc, target_soc, power_meas, battery_capacity]):
                return "Invalid parameters"

            if power_meas < 100:  # Minimum power threshold
                return "Insufficient power"

            remaining_kwh = (target_soc - current_soc) * battery_capacity / 100
            if remaining_kwh <= 0:
                return "Target reached"

            efficiency = (1 - correction / 100)
            power_kw = power_meas * efficiency / 1000
            total_minutes = round((remaining_kwh / power_kw * 60), 0)
            
            if total_minutes < 1:
                return "< 1m"

            return self.format_duration(int(total_minutes * 60))

        except (TypeError, ValueError, AttributeError):
            return "Error"

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus sensor platform."""
    try:
        updater = EveusUpdater(
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            hass=hass,
        )

        sensors = [
            NumericSensor(
                updater=updater,
                name="Voltage",
                key=ATTR_VOLTAGE,
                unit=UnitOfElectricPotential.VOLT,
                device_class=SensorDeviceClass.VOLTAGE,
                icon="mdi:lightning-bolt",
                precision=0
            ),
            NumericSensor(
                updater=updater,
                name="Current", 
                key=ATTR_CURRENT,
                unit=UnitOfElectricCurrent.AMPERE,
                device_class=SensorDeviceClass.CURRENT,
                icon="mdi:current-ac",
                precision=1
            ),
            NumericSensor(
                updater=updater,
                name="Power",
                key=ATTR_POWER,
                unit=UnitOfPower.WATT,
                device_class=SensorDeviceClass.POWER,
                icon="mdi:flash",
                precision=0
            ),
            NumericSensor(
                updater=updater,
                name="Current Set",
                key=ATTR_CURRENT_SET,
                unit=UnitOfElectricCurrent.AMPERE,
                device_class=SensorDeviceClass.CURRENT,
                icon="mdi:current-ac",
                precision=0
            ),
            EnergySensor(updater, "Session Energy", ATTR_SESSION_ENERGY),
            EnergySensor(updater, "Total Energy", ATTR_TOTAL_ENERGY),
            EnergySensor(updater, "Counter A Energy", ATTR_COUNTER_A_ENERGY),
            EnergySensor(updater, "Counter B Energy", ATTR_COUNTER_B_ENERGY),
            NumericSensor(
                updater=updater,
                name="Counter A Cost",
                key=ATTR_COUNTER_A_COST,
                unit="₴",
                icon="mdi:currency-uah",
                precision=2
            ),
            NumericSensor(
                updater=updater,
                name="Counter B Cost", 
                key=ATTR_COUNTER_B_COST,
                unit="₴",
                icon="mdi:currency-uah",
                precision=2
            ),
            NumericSensor(
                updater=updater,
                name="Box Temperature",
                key=ATTR_TEMPERATURE_BOX,
                unit=UnitOfTemperature.CELSIUS,
                device_class=SensorDeviceClass.TEMPERATURE,
                icon="mdi:thermometer",
                precision=0
            ),
            NumericSensor(
                updater=updater,
                name="Plug Temperature",
                key=ATTR_TEMPERATURE_PLUG,
                unit=UnitOfTemperature.CELSIUS,
                device_class=SensorDeviceClass.TEMPERATURE,
                icon="mdi:thermometer-high",
                precision=0
            ),
            NumericSensor(
                updater=updater,
                name="Battery Voltage",
                key=ATTR_BATTERY_VOLTAGE,
                unit=UnitOfElectricPotential.VOLT,
                device_class=SensorDeviceClass.VOLTAGE,
                icon="mdi:battery",
                precision=1
            ),
            StateSensor(updater, "State", ATTR_STATE, CHARGING_STATES),
            StateSensor(updater, "Substate", ATTR_SUBSTATE, NORMAL_SUBSTATES),
            EveusGroundSensor(updater),
            NumericSensor(
                updater=updater,
                name="Session Time",
                key=ATTR_SESSION_TIME,
                unit=UnitOfTime.SECONDS,
                device_class=SensorDeviceClass.DURATION,
                icon="mdi:timer",
                precision=0
            ),
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

    except Exception as ex:
        _LOGGER.error("Error setting up sensor platform: %s", str(ex))
        raise
