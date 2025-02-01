"""Switch entities for Eveus."""
from homeassistant.helpers.entity import EntityCategory
from .base import BaseEveusSwitch

class EveusChargingSwitch(BaseEveusSwitch):
    """Charging control switch."""

    def __init__(self, client) -> None:
        """Initialize charging switch."""
        super().__init__(client)
        self._attr_name = "Stop Charging"
        self._attr_unique_id = f"{client._device_info.identifier}_charging"
        self._attr_icon = "mdi:ev-station"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        """Return if charging is enabled."""
        return self._client.state and self._client.state.enabled

    async def async_turn_on(self, **kwargs) -> None:
        """Enable charging."""
        await self._client.send_command("evseEnabled", 1)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable charging."""
        await self._client.send_command("evseEnabled", 0)

class EveusOneChargeSwitch(BaseEveusSwitch):
    """One charge mode switch."""

    def __init__(self, client) -> None:
        """Initialize one charge switch."""
        super().__init__(client)
        self._attr_name = "One Charge"
        self._attr_unique_id = f"{client._device_info.identifier}_one_charge"
        self._attr_icon = "mdi:lightning-bolt"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        """Return if one charge mode is enabled."""
        return bool(self._client.state and self._client.state.one_charge)

    async def async_turn_on(self, **kwargs) -> None:
        """Enable one charge mode."""
        await self._client.send_command("oneCharge", 1)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable one charge mode."""
        await self._client.send_command("oneCharge", 0)

class EveusResetCounterSwitch(BaseEveusSwitch):
    """Reset counter switch."""

    def __init__(self, client) -> None:
        """Initialize reset counter switch."""
        super().__init__(client)
        self._attr_name = "Reset Counter A"
        self._attr_unique_id = f"{client._device_info.identifier}_reset_counter"
        self._attr_icon = "mdi:counter"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        """Return if counter has value."""
        return self._client.state and bool(self._client.state.counter_a_energy)

    async def async_turn_on(self, **kwargs) -> None:
        """Reset counter."""
        await self._client.send_command("rstEM1", 0)

    async def async_turn_off(self, **kwargs) -> None:
        """Reset counter."""
        await self._client.send_command("rstEM1", 0)
