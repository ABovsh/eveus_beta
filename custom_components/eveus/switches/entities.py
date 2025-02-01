"""Switch entities for Eveus."""
from typing import Any
from homeassistant.helpers.entity import EntityCategory

from .base import BaseEveusSwitch

class EveusChargingSwitch(BaseEveusSwitch):
    """Charging control switch."""

    def __init__(self, client) -> None:
        """Initialize charging switch."""
        super().__init__(client, "Stop Charging", "mdi:ev-station")
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on charging."""
        await self._client.send_command("evseEnabled", 1)
        self._is_on = True

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off charging."""
        await self._client.send_command("evseEnabled", 0)
        self._is_on = False

class EveusOneChargeSwitch(BaseEveusSwitch):
    """One charge mode switch."""

    def __init__(self, client) -> None:
        """Initialize one charge switch."""
        super().__init__(client, "One Charge", "mdi:lightning-bolt")
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable one charge mode."""
        await self._client.send_command("oneCharge", 1)
        self._is_on = True

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable one charge mode."""
        await self._client.send_command("oneCharge", 0)
        self._is_on = False

class EveusResetCounterSwitch(BaseEveusSwitch):
    """Reset counter switch."""

    def __init__(self, client) -> None:
        """Initialize reset counter switch."""
        super().__init__(client, "Reset Counter A", "mdi:counter")
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Reset counter."""
        await self._client.send_command("rstEM1", 0)
        self._is_on = False

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Reset counter."""
        await self._client.send_command("rstEM1", 0)
        self._is_on = False
