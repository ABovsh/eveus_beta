"""Support for Eveus switches."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import (
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
)

from .base import EveusBaseConnection, EveusBaseEntity
from .const import DOMAIN
from .helpers import safe_float

_LOGGER = logging.getLogger(__name__)

class EveusBaseSwitch(EveusBaseEntity, SwitchEntity):
    """Base class for Eveus switches."""

    def __init__(self, connection: EveusBaseConnection, name: str, unique_id_suffix: str) -> None:
        """Initialize the switch."""
        super().__init__(connection)
        self._attr_name = name
        self._attr_unique_id = f"{connection._host}_{unique_id_suffix}"
        self._is_on = False
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._is_on

class EveusStopChargingSwitch(EveusBaseSwitch):
    """Representation of Eveus charging control switch."""

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the switch."""
        super().__init__(connection, "Stop Charging", "stop_charging")
        self._attr_icon = "mdi:ev-station"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on charging."""
        if await self._connection._send_command("evseEnabled", 1):
            self._is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off charging."""
        if await self._connection._send_command("evseEnabled", 0):
            self._is_on = False
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update state."""
        await super().async_update()
        if self.available:
            self._is_on = self._connection.state_data.get("evseEnabled") == 1

class EveusOneChargeSwitch(EveusBaseSwitch):
    """Representation of Eveus one charge switch."""

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the switch."""
        super().__init__(connection, "One Charge", "one_charge")
        self._attr_icon = "mdi:lightning-bolt"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable one charge mode."""
        if await self._connection._send_command("oneCharge", 1):
            self._is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable one charge mode."""
        if await self._connection._send_command("oneCharge", 0):
            self._is_on = False
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update state."""
        await super().async_update()
        if self.available:
            self._is_on = self._connection.state_data.get("oneCharge") == 1

class EveusResetCounterASwitch(EveusBaseSwitch):
    """Representation of Eveus reset counter A switch."""

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the switch."""
        super().__init__(connection, "Reset Counter A", "reset_counter_a")
        self._attr_icon = "mdi:counter"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Reset counter A."""
        if await self._connection._send_command("rstEM1", 0):
            self._is_on = False
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Reset counter A when turned off to match momentary behavior."""
        await self.async_turn_on()

    async def async_update(self) -> None:
        """Update state."""
        await super().async_update()
        if self.available:
            try:
                iem1_value = safe_float(self._connection.state_data.get("IEM1"))
                self._is_on = iem1_value != 0
            except (TypeError, ValueError):
                self._is_on = False

class EveusResetCounterBSwitch(EveusBaseSwitch):
    """Representation of Eveus reset counter B switch."""

    def __init__(self, connection: EveusBaseConnection) -> None:
        """Initialize the switch."""
        super().__init__(connection, "Reset Counter B", "reset_counter_b")
        self._attr_icon = "mdi:counter"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Reset counter B."""
        if await self._connection._send_command("rstEM2", 0):
            self._is_on = False
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Reset counter B when turned off to match momentary behavior."""
        await self.async_turn_on()

    async def async_update(self) -> None:
        """Update state."""
        await super().async_update()
        if self.available:
            try:
                iem2_value = safe_float(self._connection.state_data.get("IEM2"))
                self._is_on = iem2_value != 0
            except (TypeError, ValueError):
                self._is_on = False

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus switches based on config entry."""
    connection = EveusBaseConnection(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )

    switches = [
        EveusStopChargingSwitch(connection),
        EveusOneChargeSwitch(connection),
        EveusResetCounterASwitch(connection),
        EveusResetCounterBSwitch(connection),
    ]

    # Initialize entities dict if needed
    if "entities" not in hass.data[DOMAIN][entry.entry_id]:
        hass.data[DOMAIN][entry.entry_id]["entities"] = {}

    # Store switch references with unique_id as key
    hass.data[DOMAIN][entry.entry_id]["entities"]["switch"] = {
        switch.unique_id: switch for switch in switches
    }

    async_add_entities(switches)
