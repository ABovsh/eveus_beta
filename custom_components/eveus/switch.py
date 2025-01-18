"""Support for Eveus switches."""
from __future__ import annotations

import logging
from typing import Any, Final

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import (
    DOMAIN,
    CMD_EVSE_ENABLED,
    CMD_ONE_CHARGE,
    CMD_RESET_COUNTER,
    UPDATE_INTERVAL,
)
from .session_manager import SessionManager

_LOGGER = logging.getLogger(__name__)

class BaseEveusSwitch(SwitchEntity):
    """Base class for Eveus switches."""

    _attr_has_entity_name: Final = True
    _attr_should_poll = True

    def __init__(self, session_manager: SessionManager) -> None:
        """Initialize the switch."""
        self._session_manager = session_manager
        self._is_on = False
        self._attr_unique_id = f"{self._session_manager._host}_{self.name}"
        self._update_interval = UPDATE_INTERVAL

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._session_manager.available

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._is_on

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._session_manager._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._session_manager._host})",
            "configuration_url": f"http://{self._session_manager._host}",
            "suggested_area": "Garage",
        }

    async def async_update(self) -> None:
        """Update device state."""
        try:
            state = await self._session_manager.get_state()
            self._handle_state_update(state)
        except Exception as err:
            _LOGGER.error(
                "Error updating switch %s: %s",
                self.name,
                str(err),
                exc_info=True
            )

    def _handle_state_update(self, state: dict) -> None:
        """Handle state update from device."""
        raise NotImplementedError

class EveusStopChargingSwitch(BaseEveusSwitch):
    """Representation of Eveus charging control switch."""

    _attr_name = "Stop Charging"
    _attr_icon = "mdi:ev-station"
    _attr_entity_category = EntityCategory.CONFIG

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on charging."""
        success, result = await self._session_manager.send_command(
            CMD_EVSE_ENABLED,
            1,
            verify=True
        )
        if success:
            self._is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to enable charging: %s", result.get("error", "Unknown error"))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off charging."""
        success, result = await self._session_manager.send_command(
            CMD_EVSE_ENABLED,
            0,
            verify=True
        )
        if success:
            self._is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to disable charging: %s", result.get("error", "Unknown error"))

    def _handle_state_update(self, state: dict) -> None:
        """Handle state update."""
        try:
            self._is_on = bool(state.get("evseEnabled"))
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error parsing evseEnabled state: %s", str(err))

class EveusOneChargeSwitch(BaseEveusSwitch):
    """Representation of Eveus one charge switch."""

    _attr_name = "One Charge"
    _attr_icon = "mdi:lightning-bolt"
    _attr_entity_category = EntityCategory.CONFIG

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable one charge mode."""
        success, result = await self._session_manager.send_command(
            CMD_ONE_CHARGE,
            1,
            verify=True
        )
        if success:
            self._is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to enable one charge mode: %s", result.get("error", "Unknown error"))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable one charge mode."""
        success, result = await self._session_manager.send_command(
            CMD_ONE_CHARGE,
            0,
            verify=True
        )
        if success:
            self._is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to disable one charge mode: %s", result.get("error", "Unknown error"))

    def _handle_state_update(self, state: dict) -> None:
        """Handle state update."""
        try:
            self._is_on = bool(state.get("oneCharge"))
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error parsing oneCharge state: %s", str(err))

class EveusResetCounterASwitch(BaseEveusSwitch):
    """Representation of Eveus reset counter A switch."""

    _attr_name = "Reset Counter A"
    _attr_icon = "mdi:counter"
    _attr_entity_category = EntityCategory.CONFIG

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Reset counter A."""
        success, result = await self._session_manager.send_command(
            CMD_RESET_COUNTER,
            0,
            verify=False  # Reset doesn't need verification
        )
        if success:
            self._is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to reset counter: %s", result.get("error", "Unknown error"))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Reset command for off state."""
        await self.async_turn_on()  # Reuse turn_on logic

    def _handle_state_update(self, state: dict) -> None:
        """Handle state update."""
        try:
            iem1_value = state.get("IEM1")
            if iem1_value in (None, "null", "", "undefined", "ERROR"):
                self._is_on = False
            else:
                self._is_on = float(iem1_value) != 0
        except (TypeError, ValueError) as err:
            _LOGGER.error("Error parsing IEM1 state: %s", str(err))
            self._is_on = False

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus switches based on config entry."""
    session_manager = hass.data[DOMAIN][entry.entry_id]["session_manager"]

    switches = [
        EveusStopChargingSwitch(session_manager),
        EveusOneChargeSwitch(session_manager),
        EveusResetCounterASwitch(session_manager),
    ]

    # Store entity references
    hass.data[DOMAIN][entry.entry_id]["entities"]["switch"] = {
        switch.unique_id: switch for switch in switches
    }

    async_add_entities(switches)
