"""Support for Eveus switches."""
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN

class EveusBaseSwitch(SwitchEntity):
    def __init__(self, client) -> None:
        self._client = client
        self._client.register_entity(self)
        self._attr_has_entity_name = True
    
    @property
    def available(self) -> bool:
        return self._client.available

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._client._device_info.identifier)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._client._device_info.host})",
        }

class EveusChargingSwitch(EveusBaseSwitch):
    def __init__(self, client) -> None:
        super().__init__(client)
        self._attr_name = "Stop Charging"
        self._attr_unique_id = f"{client._device_info.identifier}_charging"
        self._attr_icon = "mdi:ev-station"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        return self._client.state and self._client.state.enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self._client.send_command("evseEnabled", 1)

    async def async_turn_off(self, **kwargs) -> None:
        await self._client.send_command("evseEnabled", 0)

class EveusOneChargeSwitch(EveusBaseSwitch):
    def __init__(self, client) -> None:
        super().__init__(client)
        self._attr_name = "One Charge"
        self._attr_unique_id = f"{client._device_info.identifier}_one_charge"
        self._attr_icon = "mdi:lightning-bolt"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        return bool(self._client.state and self._client.state.one_charge)

    async def async_turn_on(self, **kwargs) -> None:
        await self._client.send_command("oneCharge", 1)

    async def async_turn_off(self, **kwargs) -> None:
        await self._client.send_command("oneCharge", 0)

class EveusResetCounterSwitch(EveusBaseSwitch):
    def __init__(self, client) -> None:
        super().__init__(client)
        self._attr_name = "Reset Counter A"
        self._attr_unique_id = f"{client._device_info.identifier}_reset_counter"
        self._attr_icon = "mdi:counter"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        if not self._client.state:
            return False
        return self._client.state.counter_a_energy > 0

    async def async_turn_on(self, **kwargs) -> None:
        await self._client.send_command("rstEM1", 0)

    async def async_turn_off(self, **kwargs) -> None:
        await self._client.send_command("rstEM1", 0)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    switches = [
        EveusChargingSwitch(client),
        EveusOneChargeSwitch(client),
        EveusResetCounterSwitch(client),
    ]
    async_add_entities(switches)
