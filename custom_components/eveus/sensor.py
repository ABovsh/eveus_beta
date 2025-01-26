"""Support for Eveus sensors."""
from __future__ import annotations
import logging
import asyncio
import time
from typing import Any
import aiohttp
from datetime import datetime

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

from .mixins import SessionMixin, DeviceInfoMixin, ErrorHandlingMixin

_LOGGER = logging.getLogger(__name__)

class EveusUpdater(SessionMixin, ErrorHandlingMixin):
    """Handle Eveus data updates."""

    def __init__(self, host: str, username: str, password: str, hass: HomeAssistant) -> None:
        """Initialize updater."""
        super().__init__(host, username, password)
        self._hass = hass
        self._data = {}
        self._sensors = []
        self._update_task = None
        self._last_update = time.time()
        self._update_lock = asyncio.Lock()
        self._retry_interval = 5
        self._backoff_factor = 1.5
        self._max_retry_interval = 300

    def register_sensor(self, sensor: "BaseEveusSensor") -> None:
        """Register a sensor for updates."""
        self._sensors.append(sensor)

    @property
    def data(self) -> dict:
        """Return latest data."""
        return self._data

    @property
    def last_update(self) -> float:
        """Return last update timestamp."""
        return self._last_update

    async def async_start_updates(self) -> None:
        """Start the update loop."""
        if self._update_task is None:
            self._update_task = asyncio.create_task(self._update_loop())

    async def _update_loop(self) -> None:
        """Handle the update loop."""
        retry_count = 0
        while True:
            try:
                async with asyncio.timeout(10):
                    await self._update()
                    retry_count = 0
                    self._retry_interval = 5
                await asyncio.sleep(SCAN_INTERVAL.total_seconds())
                
            except asyncio.CancelledError:
                break
                
            except Exception as err:
                retry_count += 1
                self._retry_interval = min(
                    self._retry_interval * self._backoff_factor,
                    self._max_retry_interval
                )
                await self.handle_error(err, f"Update failed, retrying in {self._retry_interval}s")
                await asyncio.sleep(self._retry_interval)

    async def _update(self) -> None:
        """Update data from the device."""
        async with self._update_lock:
            try:
                session = await self._get_session()
                async with session.post(
                    f"http://{self._host}/main",
                    auth=aiohttp.BasicAuth(self._username, self._password),
                    timeout=10
                ) as response:
                    response.raise_for_status()
                    if response.content_length == 0:
                        raise ValueError("Empty response received")
                        
                    data = await response.json()
                    if not isinstance(data, dict):
                        raise ValueError("Invalid data format received")
                        
                    self._data = data
                    self._available = True
                    self._last_update = time.time()
                    self._error_count = 0

                    for sensor in self._sensors:
                        try:
                            sensor.async_write_ha_state()
                        except Exception as err:
                            await self.handle_error(err, f"Error updating sensor {getattr(sensor, 'name', 'unknown')}")

            except Exception as err:
                self._error_count += 1
                self._available = self._error_count < self._max_errors
                raise

    async def async_shutdown(self) -> None:
        """Shut down the updater."""
        if self._update_task:
            self._update_task.cancel()
            try:
                async with asyncio.timeout(5):
                    await self._update_task
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        await self._cleanup_session()

class BaseEveusSensor(DeviceInfoMixin, SensorEntity, RestoreEntity):
    """Base implementation for Eveus sensors."""
    
    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
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
        state = await self.async_get_last_state()
        if state and state.state not in ('unknown', 'unavailable'):
            try:
                self._previous_value = (
                    float(state.state) 
                    if hasattr(self, '_attr_suggested_display_precision') 
                    else state.state
                )
            except (TypeError, ValueError):
                self._previous_value = state.state
        await self._updater.async_start_updates()

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal."""
        await self._updater.async_shutdown()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._updater.available

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {
            "last_update": self._updater.last_update,
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
        """Initialize the sensor."""
        super().__init__(updater)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{updater._host}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_icon = icon
        self._attr_suggested_display_precision = precision
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        try:
            value = float(self._updater.data.get(self._key, 0))
            self._previous_value = value
            if self._attr_suggested_display_precision is not None:
                return round(value, self._attr_suggested_display_precision)
            return value
        except (TypeError, ValueError):
            return self._previous_value

class EnergySensor(NumericSensor):
    """Base energy sensor."""
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
    """Base state sensor."""
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
        try:
            state = self._updater.data.get(self._key)
            return self._state_map.get(state, "Unknown")
        except (TypeError, ValueError):
            return "Unknown"

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
        try:
            return "Connected" if self._updater.data.get(ATTR_GROUND) == 1 else "Not Connected"
        except (TypeError, ValueError):
            return "Unknown"

class EVSocKwhSensor(BaseEveusSensor):
    """EV State of Charge energy sensor."""
    
    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the sensor."""
        super().__init__(updater)
        return None

class TimeToTargetSocSensor(TextEntity, DeviceInfoMixin):
    """Time to target SOC text entity."""
    _attr_icon = "mdi:timer"
    _attr_pattern = None
    _attr_mode = "text"

    def __init__(self, updater: EveusUpdater) -> None:
        """Initialize the text entity."""
        super().__init__()
        self._updater = updater
        self._attr_name = "Time to Target"
        self._attr_unique_id = f"{updater._host}_time_to_target"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._updater.available

    @property
    def native_value(self) -> str:
        """Calculate and return formatted time to target."""
        try:
            if self._updater.data.get(ATTR_STATE) != 4:  # Not charging
                return "Standby"

            current_soc = float(self.hass.states.get("sensor.eveus_ev_charger_soc_percent").state)
            target_soc = float(self.hass.states.get("input_number.ev_target_soc").state)
            power_meas = float(self._updater.data.get(ATTR_POWER, 0))
            battery_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
            correction = float(self.hass.states.get("input_number.ev_soc_correction").state)

            if power_meas <= 0:
                return "Standby"

            remaining_kwh = (target_soc - current_soc) * battery_capacity / 100
            efficiency = (1 - correction / 100)
            power_kw = power_meas * efficiency / 1000
            
            if power_kw <= 0:
                return "Standby"

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
