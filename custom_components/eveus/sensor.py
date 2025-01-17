"""Support for Eveus sensors."""
from __future__ import annotations

import logging
import asyncio
import time
from datetime import datetime
from typing import Any, Final

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util
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
    PERCENTAGE,
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
    API_ENDPOINT_MAIN,
    COMMAND_TIMEOUT,
    MAX_RETRIES,
    RETRY_DELAY,
    MIN_UPDATE_INTERVAL,
    HELPER_EV_BATTERY_CAPACITY,
    HELPER_EV_INITIAL_SOC,
    HELPER_EV_SOC_CORRECTION,
    HELPER_EV_TARGET_SOC,
)

_LOGGER = logging.getLogger(__name__)

class EveusUpdater:
    """Class to manage Eveus data updates."""

    def __init__(
        self, 
        host: str, 
        username: str, 
        password: str, 
        hass: HomeAssistant
    ) -> None:
        """Initialize the updater."""
        self._host = host
        self._username = username
        self._password = password
        self._hass = hass
        self._data: dict[str, Any] = {}
        self._available = True
        self._session = None
        self._sensors: list[BaseEveusSensor] = []
        self._update_task = None
        self._last_update = time.time()
        self._update_lock = asyncio.Lock()
        self._error_count = 0
        self._max_errors = 3
        self._current_retry_delay = RETRY_DELAY

    def register_sensor(self, sensor: BaseEveusSensor) -> None:
        """Register a sensor for updates."""
        self._sensors.append(sensor)

    @property
    def data(self) -> dict[str, Any]:
        """Return the latest data."""
        return self._data

    @property
    def available(self) -> bool:
        """Return if updater is available."""
        return self._available

    @property
    def last_update(self) -> float:
        """Return last update time."""
        return self._last_update

    async def async_start_updates(self) -> None:
        """Start the update loop."""
        if self._update_task is None:
            self._update_task = asyncio.create_task(self._update_loop())

    async def _update_loop(self) -> None:
        """Handle updates with improved error handling and backoff."""
        while True:
            try:
                await self._update()
                # Reset retry delay on successful update
                self._current_retry_delay = RETRY_DELAY
                await asyncio.sleep(SCAN_INTERVAL.total_seconds())
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error in update loop: %s", str(err))
                await asyncio.sleep(self._current_retry_delay)
                self._current_retry_delay = min(self._current_retry_delay * 2, 300)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create client session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=COMMAND_TIMEOUT)
            connector = aiohttp.TCPConnector(
                limit=1,
                force_close=True,
                enable_cleanup_closed=True
            )
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                raise_for_status=True
            )
        return self._session

    async def _update(self) -> None:
        """Update the data with comprehensive error handling."""
        if time.time() - self._last_update < MIN_UPDATE_INTERVAL:
            return

        async with self._update_lock:
            for attempt in range(MAX_RETRIES):
                try:
                    session = await self._get_session()
                    async with session.post(
                        f"http://{self._host}{API_ENDPOINT_MAIN}",
                        auth=aiohttp.BasicAuth(self._username, self._password),
                        timeout=COMMAND_TIMEOUT
                    ) as response:
                        self._data = await response.json()
                        
                        if not all(key in self._data for key in [ATTR_STATE, ATTR_ENABLED]):
                            raise ValueError("Missing critical data points")
                        
                        self._available = True
                        self._last_update = time.time()
                        self._error_count = 0

                        failed_sensors = []
                        for sensor in self._sensors:
                            try:
                                sensor.async_write_ha_state()
                            except Exception as sensor_err:
                                failed_sensors.append(sensor.entity_id)
                                _LOGGER.error(
                                    "Error updating sensor %s: %s",
                                    sensor.entity_id,
                                    str(sensor_err)
                                )
                        
                        if failed_sensors:
                            _LOGGER.warning(
                                "Failed to update the following sensors: %s",
                                ", ".join(failed_sensors)
                            )
                        return

                except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                    if attempt + 1 >= MAX_RETRIES:
                        self._error_count += 1
                        self._available = self._error_count < self._max_errors
                        _LOGGER.error("Connection error: %s", str(err))
                        return
                    await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                
                except Exception as err:
                    self._error_count += 1
                    self._available = self._error_count < self._max_errors
                    _LOGGER.error("Unexpected error updating data: %s", str(err))
                    return

    async def async_shutdown(self) -> None:
        """Shutdown the updater and cleanup resources."""
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
            
        if self._session and not self._session.closed:
            await self._session.close()
            
        self._sensors.clear()

class BaseEveusSensor(SensorEntity, RestoreEntity):
    """Base implementation for all Eveus sensors."""

    _attr_has_entity_name: Final = True
    _attr_should_poll: Final = False
    _attr_entity_registry_enabled_default: Final = True
    _attr_entity_registry_visible_default: Final = True

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        self._updater = updater
        self._updater.register_sensor(self)
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
        await self._updater.async_start_updates()

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal."""
        await self._updater.async_shutdown()

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._updater._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._updater._host})",
            "sw_version": self._updater.data.get("verFWMain", "Unknown"),
            "hw_version": self._updater.data.get("verHW", "Unknown"),
            "configuration_url": f"http://{self._updater._host}",
            "suggested_area": "Garage",
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {
            "last_update": dt_util.as_local(
                datetime.fromtimestamp(self._updater.last_update)
            ).isoformat(),
            "host": self._updater._host,
        }
        if self._previous_value is not None:
            attrs["previous_value"] = self._previous_value
        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._updater.available

class EveusNumericSensor(BaseEveusSensor):
    """Base class for numeric sensors."""

    _attr_suggested_display_precision: Final = 2

    @property
    def native_value(self) -> float | None:
        """Return the sensor value with validation."""
        try:
            value = self._updater.data.get(self._key)
            if value is None:
                return self._previous_value
                
            value = float(value)
            if not -1e6 <= value <= 1e6:
                _LOGGER.warning(
                    "Value out of reasonable range for %s: %f",
                    self.entity_id,
                    value
                )
                return self._previous_value
                
            self._previous_value = value
            return round(value, self._attr_suggested_display_precision)
        except (TypeError, ValueError) as err:
            _LOGGER.debug(
                "Error converting value for %s: %s",
                self.entity_id,
                str(err)
            )
            return self._previous_value

class EveusEnergyBaseSensor(EveusNumericSensor):
    """Base energy sensor with improved precision."""
    
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return energy value with additional validation."""
        value = super().native_value
        if value is not None and value < 0:
            _LOGGER.warning(
                "Negative energy value detected for %s: %f",
                self.entity_id,
                value
            )
            return self._previous_value
        return value

class EveusVoltageSensor(EveusNumericSensor):
    """Voltage sensor."""
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:lightning-bolt"
    _attr_suggested_display_precision = 0
    _key = ATTR_VOLTAGE
    _attr_translation_key = "voltage"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Voltage"
        self._attr_unique_id = f"{updater._host}_voltage"

    @property
    def native_value(self) -> float | None:
        """Return voltage with range validation."""
        value = super().native_value
        if value is not None and not 180 <= value <= 260:
            _LOGGER.warning("Voltage out of normal range: %f V", value)
        return value

class EveusCurrentSensor(EveusNumericSensor):
    """Current sensor."""
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:current-ac"
    _attr_suggested_display_precision = 1
    _key = ATTR_CURRENT
    _attr_translation_key = "current"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Current"
        self._attr_unique_id = f"{updater._host}_current"

class EveusPowerSensor(EveusNumericSensor):
    """Power sensor."""
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:flash"
    _attr_suggested_display_precision = 0
    _key = ATTR_POWER
    _attr_translation_key = "power"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Power"
        self._attr_unique_id = f"{updater._host}_power"

class EveusCurrentSetSensor(EveusNumericSensor):
    """Current set sensor."""
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:current-ac"
    _key = ATTR_CURRENT_SET
    _attr_translation_key = "charging_current"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Current Set"
        self._attr_unique_id = f"{updater._host}_current_set"

class EveusSessionEnergySensor(EveusEnergyBaseSensor):
    """Session energy sensor."""
    _key = ATTR_SESSION_ENERGY
    _attr_icon = "mdi:battery-charging"
    _attr_translation_key = "session_energy"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Session Energy"
        self._attr_unique_id = f"{updater._host}_session_energy"

class EveusTotalEnergySensor(EveusEnergyBaseSensor):
    """Total energy sensor."""
    _key = ATTR_TOTAL_ENERGY
    _attr_icon = "mdi:battery-charging-100"
    _attr_translation_key = "total_energy"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Total Energy"
        self._attr_unique_id = f"{updater._host}_total_energy"

class EveusStateSensor(BaseEveusSensor):
    """Charging state sensor."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information"
    _attr_translation_key = "state"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "State"
        self._attr_unique_id = f"{updater._host}_state"

    @property
    def native_value(self) -> str:
        """Return charging state with validation."""
        try:
            state = self._updater.data.get(ATTR_STATE)
            if state is None:
                return "Unknown"
            
            state = int(state)
            if state not in CHARGING_STATES:
                _LOGGER.warning("Unknown charging state: %d", state)
                return "Unknown"
                
            return CHARGING_STATES[state]
        except (TypeError, ValueError):
            return "Unknown"

class EveusSubstateSensor(BaseEveusSensor):
    """Substate sensor with enhanced error detection."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information"
    _attr_translation_key = "substate"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Substate"
        self._attr_unique_id = f"{updater._host}_substate"

    @property
    def native_value(self) -> str:
        """Return substate with enhanced context and validation."""
        try:
            state = self._updater.data.get(ATTR_STATE)
            substate = self._updater.data.get(ATTR_SUBSTATE)
            
            if state is None or substate is None:
                return "Unknown"
                
            state = int(state)
            substate = int(substate)
            
            if state == 7:  # Error state
                if substate not in ERROR_STATES:
                    _LOGGER.warning("Unknown error state: %d", substate)
                    return "Unknown Error"
                return ERROR_STATES[substate]
                
            if substate not in NORMAL_SUBSTATES:
                _LOGGER.warning("Unknown substate: %d", substate)
                return "Unknown State"
                
            return NORMAL_SUBSTATES[substate]
            
        except (TypeError, ValueError):
            return "Unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes
        try:
            state = int(self._updater.data.get(ATTR_STATE, -1))
            substate = int(self._updater.data.get(ATTR_SUBSTATE, -1))
            attrs["state_code"] = state
            attrs["substate_code"] = substate
        except (TypeError, ValueError):
            pass
        return attrs

class EveusEnabledSensor(BaseEveusSensor):
    """Enabled state sensor."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:power"
    _attr_translation_key = "enabled"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Enabled"
        self._attr_unique_id = f"{updater._host}_enabled"

    @property
    def native_value(self) -> str:
        """Return if charging is enabled."""
        try:
            return "Yes" if int(self._updater.data.get(ATTR_ENABLED, 0)) == 1 else "No"
        except (TypeError, ValueError):
            return "Unknown"

class EveusGroundSensor(BaseEveusSensor):
    """Ground sensor."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:electric-switch"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["Connected", "Not Connected", "Unknown"]
    _attr_translation_key = "ground"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Ground"
        self._attr_unique_id = f"{updater._host}_ground"

    @property
    def native_value(self) -> str:
        """Return ground status."""
        try:
            return "Connected" if int(self._updater.data.get(ATTR_GROUND, 0)) == 1 else "Not Connected"
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
    _attr_translation_key = "box_temperature"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Box Temperature"
        self._attr_unique_id = f"{updater._host}_box_temperature"

    @property
    def native_value(self) -> float | None:
        """Return temperature with safety validation."""
        value = super().native_value
        if value is not None:
            if value > 80:
                _LOGGER.warning("Box temperature critically high: %f°C", value)
            elif value > 60:
                _LOGGER.warning("Box temperature high: %f°C", value)
        return value

class EveusPlugTemperatureSensor(EveusNumericSensor):
    """Plug temperature sensor."""
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:thermometer-high"
    _key = ATTR_TEMPERATURE_PLUG
    _attr_translation_key = "plug_temperature"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Plug Temperature"
        self._attr_unique_id = f"{updater._host}_plug_temperature"

    @property
    def native_value(self) -> float | None:
        """Return temperature with safety validation."""
        value = super().native_value
        if value is not None:
            if value > 65:
                _LOGGER.warning("Plug temperature critically high: %f°C", value)
            elif value > 50:
                _LOGGER.warning("Plug temperature high: %f°C", value)
        return value

class EveusSystemTimeSensor(BaseEveusSensor):
    """System time sensor."""
    _attr_icon = "mdi:clock-outline"
    _attr_translation_key = "system_time"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "System Time"
        self._attr_unique_id = f"{updater._host}_system_time"

    @property
    def native_value(self) -> str:
        """Return formatted system time."""
        try:
            timestamp = int(self._updater.data.get(ATTR_SYSTEM_TIME, 0))
            local_time = dt_util.as_local(datetime.fromtimestamp(timestamp))
            return local_time.strftime("%H:%M")
        except (TypeError, ValueError, OSError):
            return "unknown"

class EveusSessionTimeSensor(BaseEveusSensor):
    """Session time sensor."""
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:timer"
    _attr_translation_key = "session_time"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Session Time"
        self._attr_unique_id = f"{updater._host}_session_time"
    
    @property
    def native_value(self) -> int:
        """Return the session time in seconds."""
        try:
            return int(self._updater.data.get(ATTR_SESSION_TIME, 0))
        except (TypeError, ValueError):
            return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes
        try:
            seconds = int(self._updater.data.get(ATTR_SESSION_TIME, 0))
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
            attrs["days"] = days
            attrs["hours"] = hours
            attrs["minutes"] = minutes
            
        except (TypeError, ValueError):
            attrs["formatted_time"] = "0m"
            
        return attrs

class EveusCounterAEnergySensor(EveusEnergyBaseSensor):
    """Counter A energy sensor."""
    _key = ATTR_COUNTER_A_ENERGY
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:counter"
    _attr_translation_key = "counter_a_energy"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Counter A Energy"
        self._attr_unique_id = f"{updater._host}_counter_a_energy"

class EveusCounterBEnergySensor(EveusEnergyBaseSensor):
    """Counter B energy sensor."""
    _key = ATTR_COUNTER_B_ENERGY
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:counter"
    _attr_translation_key = "counter_b_energy"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Counter B Energy"
        self._attr_unique_id = f"{updater._host}_counter_b_energy"

class EveusCounterACostSensor(EveusNumericSensor):
    """Counter A cost sensor."""
    _attr_native_unit_of_measurement = "₴"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:currency-uah"
    _key = ATTR_COUNTER_A_COST
    _attr_translation_key = "counter_a_cost"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Counter A Cost"
        self._attr_unique_id = f"{updater._host}_counter_a_cost"

class EveusCounterBCostSensor(EveusNumericSensor):
    """Counter B cost sensor."""
    _attr_native_unit_of_measurement = "₴"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:currency-uah"
    _key = ATTR_COUNTER_B_COST
    _attr_translation_key = "counter_b_cost"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Counter B Cost"
        self._attr_unique_id = f"{updater._host}_counter_b_cost"

class EveusBatteryVoltageSensor(EveusNumericSensor):
    """Battery voltage sensor."""
    _attr_device_class = SensorDeviceClass.VOLTAGE  
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery"
    _key = ATTR_BATTERY_VOLTAGE
    _attr_translation_key = "battery_voltage"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Battery Voltage"
        self._attr_unique_id = f"{updater._host}_battery_voltage"

    @property
    def native_value(self) -> float | None:
        """Return battery voltage with validation."""
        value = super().native_value
        if value is not None:
            if value < 2.5:
                _LOGGER.warning("Battery voltage critically low: %f V", value)
            elif value < 2.7:
                _LOGGER.warning("Battery voltage low: %f V", value)
        return value

class EVSocKwhSensor(BaseEveusSensor):
    """EV State of Charge energy sensor."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:battery-charging"
    _attr_suggested_display_precision = 1
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "soc_energy"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "SOC Energy"
        self._attr_unique_id = f"{updater._host}_soc_kwh"

    @property
    def native_value(self) -> float | None:
        """Calculate and return state of charge in kWh with validation."""
        try:
            initial_soc = float(self.hass.states.get(HELPER_EV_INITIAL_SOC).state)
            max_capacity = float(self.hass.states.get(HELPER_EV_BATTERY_CAPACITY).state)
            energy_charged = float(self._updater.data.get(ATTR_COUNTER_A_ENERGY, 0))
            correction = float(self.hass.states.get(HELPER_EV_SOC_CORRECTION).state)

            # Validate inputs
            if not (0 <= initial_soc <= 100 and max_capacity > 0 and 0 <= correction <= 10):
                _LOGGER.warning("Invalid input parameters for SOC calculation")
                return None

            initial_kwh = (initial_soc / 100) * max_capacity
            efficiency = (1 - correction / 100)
            charged_kwh = energy_charged * efficiency
            total_kwh = initial_kwh + charged_kwh
            
            # Ensure result is within valid range
            result = max(0, min(total_kwh, max_capacity))
            return round(result, 1)

        except (TypeError, ValueError, AttributeError) as err:
            _LOGGER.debug("Error calculating SOC: %s", str(err))
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes
        try:
            attrs.update({
                "initial_soc_kwh": (float(self.hass.states.get(HELPER_EV_INITIAL_SOC).state) / 100) * 
                                 float(self.hass.states.get(HELPER_EV_BATTERY_CAPACITY).state),
                "energy_charged": float(self._updater.data.get(ATTR_COUNTER_A_ENERGY, 0)),
                "efficiency": 1 - float(self.hass.states.get(HELPER_EV_SOC_CORRECTION).state) / 100,
            })
        except (TypeError, ValueError, AttributeError):
            pass
        return attrs

class EVSocPercentSensor(BaseEveusSensor):
    """EV State of Charge percentage sensor."""
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:battery-charging"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_translation_key = "soc_percent"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "SOC Percent"
        self._attr_unique_id = f"{updater._host}_soc_percent"

    @property
    def native_value(self) -> float | None:
        """Return the state of charge percentage with validation."""
        try:
            soc_kwh = float(self.hass.states.get(f"sensor.{self._updater._host}_soc_energy").state)
            max_capacity = float(self.hass.states.get(HELPER_EV_BATTERY_CAPACITY).state)
            
            if soc_kwh >= 0 and max_capacity > 0:
                percentage = round((soc_kwh / max_capacity * 100), 0)
                return max(0, min(percentage, 100))
            return None
        except (TypeError, ValueError, AttributeError) as err:
            _LOGGER.debug("Error calculating SOC percentage: %s", str(err))
            return None

class TimeToTargetSocSensor(BaseEveusSensor):
    """Time to target SOC sensor."""
    _attr_icon = "mdi:timer"
    _attr_translation_key = "time_to_target"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        self._attr_name = "Time to Target"
        self._attr_unique_id = f"{updater._host}_time_to_target"

    @property
    def native_value(self) -> str:
        """Calculate and return time to target SOC with enhanced status reporting."""
        try:
            if int(self._updater.data.get(ATTR_STATE, 0)) != 4:  # Not charging
                charging_state = CHARGING_STATES.get(
                    int(self._updater.data.get(ATTR_STATE, -1)), 
                    "Unknown"
                )
                return f"Not charging ({charging_state})"

            current_soc = float(self.hass.states.get(f"sensor.{self._updater._host}_soc_percent").state)
            target_soc = float(self.hass.states.get(HELPER_EV_TARGET_SOC).state)
            
            if current_soc >= target_soc:
                return "Target reached"

            power_meas = float(self._updater.data.get(ATTR_POWER, 0))
            if power_meas < 100:
                return f"Insufficient power ({power_meas:.0f}W)"

            battery_capacity = float(self.hass.states.get(HELPER_EV_BATTERY_CAPACITY).state)
            correction = float(self.hass.states.get(HELPER_EV_SOC_CORRECTION).state)

            # Calculate remaining time
            remaining_kwh = (target_soc - current_soc) * battery_capacity / 100
            efficiency = (1 - correction / 100)
            power_kw = power_meas * efficiency / 1000
            total_minutes = round((remaining_kwh / power_kw * 60), 0)

            if total_minutes < 1:
                return "Less than 1m"

            days = int(total_minutes // 1440)
            hours = int((total_minutes % 1440) // 60)
            minutes = int(total_minutes % 60)

            if days > 0:
                return f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes}m"

        except (TypeError, ValueError, AttributeError) as err:
            _LOGGER.debug("Error calculating time to target: %s", str(err))
            return "Calculation error"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes
        try:
            attrs.update({
                "current_soc": float(self.hass.states.get(f"sensor.{self._updater._host}_soc_percent").state),
                "target_soc": float(self.hass.states.get(HELPER_EV_TARGET_SOC).state),
                "charging_power": float(self._updater.data.get(ATTR_POWER, 0)),
                "efficiency": 1 - float(self.hass.states.get(HELPER_EV_SOC_CORRECTION).state) / 100,
            })
        except (TypeError, ValueError, AttributeError):
            pass
        return attrs

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

    # Store entity references
    if "entities" not in hass.data[DOMAIN][entry.entry_id]:
        hass.data[DOMAIN][entry.entry_id]["entities"] = {}

    # Store updater reference
    if "updaters" not in hass.data[DOMAIN][entry.entry_id]:
        hass.data[DOMAIN][entry.entry_id]["updaters"] = {}
    hass.data[DOMAIN][entry.entry_id]["updaters"]["main"] = updater

    # Store sensor references with unique_id as key
    hass.data[DOMAIN][entry.entry_id]["entities"]["sensor"] = {
        sensor.unique_id: sensor for sensor in sensors
    }

    async_add_entities(sensors)
