"""Energy-related sensors."""
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfPower,
)
from .base import BaseNumericSensor

class EveusEnergySensor(BaseNumericSensor):
    """Base energy sensor."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1

class EveusVoltageSensor(BaseNumericSensor):
    """Voltage sensor."""
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, client) -> None:
        super().__init__(client)
        self._attr_name = "Voltage"
        self._attr_unique_id = f"{client._device_info.identifier}_voltage"

    def get_value_from_state(self) -> float:
        return self._client.state.voltage if self._client.state else 0

class EveusCurrentSensor(BaseNumericSensor):
    """Current sensor."""
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:current-ac"

    def __init__(self, client) -> None:
        super().__init__(client)
        self._attr_name = "Current"
        self._attr_unique_id = f"{client._device_info.identifier}_current"

    def get_value_from_state(self) -> float:
        return self._client.state.current if self._client.state else 0

class EveusPowerSensor(BaseNumericSensor):
    """Power sensor."""
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:flash"

    def __init__(self, client) -> None:
        super().__init__(client)
        self._attr_name = "Power"
        self._attr_unique_id = f"{client._device_info.identifier}_power"

    def get_value_from_state(self) -> float:
        return self._client.state.power if self._client.state else 0

class EveusSessionEnergySensor(EveusEnergySensor):
    """Session energy sensor."""
    def __init__(self, client) -> None:
        super().__init__(client)
        self._attr_name = "Session Energy"
        self._attr_unique_id = f"{client._device_info.identifier}_session_energy"
        self._attr_icon = "mdi:battery-charging"

    def get_value_from_state(self) -> float:
        return self._client.state.session_energy if self._client.state else 0

class EveusTotalEnergySensor(EveusEnergySensor):
    """Total energy sensor."""
    def __init__(self, client) -> None:
        super().__init__(client)
        self._attr_name = "Total Energy"
        self._attr_unique_id = f"{client._device_info.identifier}_total_energy"
        self._attr_icon = "mdi:battery-charging-100"

    def get_value_from_state(self) -> float:
        return self._client.state.total_energy if self._client.state else 0

class EveusCounterEnergySensor(EveusEnergySensor):
    """Base counter energy sensor."""
    _attr_icon = "mdi:counter"

class EveusCounterCostSensor(BaseNumericSensor):
    """Base counter cost sensor."""
    _attr_native_unit_of_measurement = "₴"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:currency-uah"
    _attr_suggested_display_precision = 0

class EveusCounterAEnergySensor(EveusCounterEnergySensor):
    """Counter A energy sensor."""
    def __init__(self, client) -> None:
        super().__init__(client)
        self._attr_name = "Counter A Energy"
        self._attr_unique_id = f"{client._device_info.identifier}_counter_a_energy"

    def get_value_from_state(self) -> float:
        return self._client.state.counter_a_energy if self._client.state else 0

class EveusCounterBEnergySensor(EveusCounterEnergySensor):
    """Counter B energy sensor."""
    def __init__(self, client) -> None:
        super().__init__(client)
        self._attr_name = "Counter B Energy"
        self._attr_unique_id = f"{client._device_info.identifier}_counter_b_energy"

    def get_value_from_state(self) -> float:
        return self._client.state.counter_b_energy if self._client.state else 0

class EveusCounterACostSensor(EveusCounterCostSensor):
    """Counter A cost sensor."""
    def __init__(self, client) -> None:
        super().__init__(client)
        self._attr_name = "Counter A Cost"
        self._attr_unique_id = f"{client._device_info.identifier}_counter_a_cost"

    def get_value_from_state(self) -> float:
        return self._client.state.counter_a_cost if self._client.state else 0

class EveusCounterBCostSensor(EveusCounterCostSensor):
    """Counter B cost sensor."""
    def __init__(self, client) -> None:
        super().__init__(client)
        self._attr_name = "Counter B Cost"
        self._attr_unique_id = f"{client._device_info.identifier}_counter_b_cost"

    def get_value_from_state(self) -> float:
        return self._client.state.counter_b_cost if self._client.state else 0
