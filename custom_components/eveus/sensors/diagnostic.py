"""Diagnostic sensors for Eveus."""
from typing import Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfTemperature,
    UnitOfTime,  # Added missing import
)

from .base import BaseEveusSensor, BaseNumericSensor
from ..const import CHARGING_STATES, ERROR_STATES, NORMAL_SUBSTATES
from ..util.helpers import format_duration, format_system_time

class EveusStateSensor(BaseEveusSensor):
    """Charging state sensor."""
    
    def __init__(self, client) -> None:
        """Initialize the sensor."""
        super().__init__(client)
        self._attr_name = "State"
        self._attr_unique_id = f"{client._device_info.identifier}_state"
        self._attr_icon = "mdi:information"

    @property
    def native_value(self) -> str:
        """Return charging state."""
        if not self._client.state:
            return "Unknown"
        return CHARGING_STATES.get(self._client.state.state, "Unknown")

class EveusSubstateSensor(BaseEveusSensor):
    """Substate sensor."""
    
    def __init__(self, client) -> None:
        """Initialize the sensor."""
        super().__init__(client)
        self._attr_name = "Substate"
        self._attr_unique_id = f"{client._device_info.identifier}_substate"
        self._attr_icon = "mdi:information"

    @property
    def native_value(self) -> str:
        """Return substate with context."""
        if not self._client.state:
            return "Unknown"
            
        state = self._client.state.state
        substate = self._client.state.substate
        
        if state == 7:  # Error state
            return ERROR_STATES.get(substate, "Unknown Error")
        return NORMAL_SUBSTATES.get(substate, "Unknown State")

class EveusTemperatureSensor(BaseNumericSensor):
    """Temperature sensor base class."""
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

class EveusBoxTemperatureSensor(EveusTemperatureSensor):
    """Box temperature sensor."""
    
    def __init__(self, client) -> None:
        """Initialize the sensor."""
        super().__init__(client)
        self._attr_name = "Box Temperature"
        self._attr_unique_id = f"{client._device_info.identifier}_box_temperature"
        self._attr_icon = "mdi:thermometer"

    def get_value_from_state(self) -> float:
        """Get box temperature value."""
        return self._client.state.temperature_box

class EveusPlugTemperatureSensor(EveusTemperatureSensor):
    """Plug temperature sensor."""
    
    def __init__(self, client) -> None:
        """Initialize the sensor."""
        super().__init__(client)
        self._attr_name = "Plug Temperature"
        self._attr_unique_id = f"{client._device_info.identifier}_plug_temperature"
        self._attr_icon = "mdi:thermometer-high"

    def get_value_from_state(self) -> float:
        """Get plug temperature value."""
        return self._client.state.temperature_plug

class EveusSystemTimeSensor(BaseEveusSensor):
    """System time sensor."""

    def __init__(self, client) -> None:
        """Initialize the sensor."""
        super().__init__(client)
        self._attr_name = "System Time"
        self._attr_unique_id = f"{client._device_info.identifier}_system_time"
        self._attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> str:
        """Return formatted system time."""
        if not self._client.state:
            return "unknown"
        return format_system_time(self._client.state.system_time)

class EveusSessionTimeSensor(BaseEveusSensor):
    """Session time sensor."""
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, client) -> None:
        """Initialize the sensor."""
        super().__init__(client)
        self._attr_name = "Session Time"
        self._attr_unique_id = f"{client._device_info.identifier}_session_time"
        self._attr_icon = "mdi:timer"

    @property
    def native_value(self) -> int:
        """Return session time in seconds."""
        if not self._client.state:
            return 0
        return self._client.state.session_time

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        attrs = super().extra_state_attributes
        if not self._client.state:
            return attrs
            
        attrs["formatted_time"] = format_duration(self._client.state.session_time)
        return attrs
