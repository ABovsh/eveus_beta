"""Base class for switches."""
from homeassistant.components.switch import SwitchEntity

class BaseEveusSwitch(SwitchEntity):
    """Base Eveus switch."""

    def __init__(self, client) -> None:
        """Initialize the switch."""
        self._client = client
        self._client.register_entity(self)
        self._attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._client.available

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._client._device_info.identifier)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._client._device_info.host})",
        }
