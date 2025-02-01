"""Base switch implementation for Eveus."""
from typing import Any
from homeassistant.components.switch import SwitchEntity
from ..api.client import EveusClient
from ..const import DOMAIN

class BaseEveusSwitch(SwitchEntity):
    """Base implementation of Eveus switch."""

    def __init__(self, client: EveusClient, name: str, icon: str) -> None:
        """Initialize switch."""
        self._client = client
        self._attr_name = name
        self._attr_icon = icon
        self._attr_has_entity_name = True
        self._is_on = False

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"{self._client._device_info.identifier}_{self.name}"

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._client.available

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._client._device_info.identifier)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._client._device_info.host})",
        }
