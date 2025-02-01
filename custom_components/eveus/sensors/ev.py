"""EV-specific sensors for Eveus."""
from typing import Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfEnergy,
    PERCENTAGE,
)

from .base import BaseEveusSensor
from ..util.helpers import calculate_soc_kwh

class EVSocKwhSensor(BaseEveusSensor):
    """EV State of Charge energy sensor."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, client) -> None:
        """Initialize the sensor."""
        super().__init__(client)
        self._attr_name = "SOC Energy"
        self._attr_unique_id = f"{client._device_info.identifier}_soc_kwh"
        self._attr_icon = "mdi:battery-charging"
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> Optional[float]:
        """Calculate and return state of charge in kWh."""
        try:
            initial_soc = float(self.hass.states.get("input_number.ev_initial_soc").state)
            max_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
            energy_charged = self._client.state.counter_a_energy
            correction = float(self.hass.states.get("input_number.ev_soc_correction").state)

            return calculate_soc_kwh(initial_soc, max_capacity, energy_charged, correction)
        except (TypeError, ValueError, AttributeError):
            return None

class EVSocPercentSensor(BaseEveusSensor):
    """EV State of Charge percentage sensor."""
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, client) -> None:
        """Initialize the sensor."""
        super().__init__(client)
        self._attr_name = "SOC Percent"
        self._attr_unique_id = f"{client._device_info.identifier}_soc_percent"
        self._attr_icon = "mdi:battery-charging"

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of charge percentage."""
        try:
            soc_kwh = float(self.hass.states.get(f"sensor.eveus_ev_charger_soc_energy").state)
            max_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
            
            if soc_kwh >= 0 and max_capacity > 0:
                percentage = round((soc_kwh / max_capacity * 100), 0)
                return max(0, min(percentage, 100))
            return None
        except (TypeError, ValueError, AttributeError):
            return None

class TimeToTargetSocSensor(BaseEveusSensor):
    """Time to target SOC sensor."""

    def __init__(self, client) -> None:
        """Initialize the sensor."""
        super().__init__(client)
        self._attr_name = "Time to Target"
        self._attr_unique_id = f"{client._device_info.identifier}_time_to_target"
        self._attr_icon = "mdi:timer"

    @property
    def native_value(self) -> str:
        """Calculate and return formatted time to target."""
        try:
            if not self._client.state:
                return "-"

            current_soc = float(self.hass.states.get(f"sensor.eveus_ev_charger_soc_percent").state)
            target_soc = float(self.hass.states.get("input_number.ev_target_soc").state)
            power_meas = self._client.state.power
            battery_capacity = float(self.hass.states.get("input_number.ev_battery_capacity").state)
            correction = float(self.hass.states.get("input_number.ev_soc_correction").state)

            if current_soc >= target_soc:
                return "Target reached"

            if not self._client.state.power:
                return "Not charging"

            if power_meas < 100:
                return "Insufficient power"

            remaining_kwh = (target_soc - current_soc) * battery_capacity / 100
            efficiency = (1 - correction / 100)
            power_kw = power_meas * efficiency / 1000
            total_minutes = round((remaining_kwh / power_kw * 60), 0)

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
