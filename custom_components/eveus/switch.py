"""Support for Eveus switches."""
from __future__ import annotations

import logging
import asyncio
import time
from typing import Any, Final

import aiohttp

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

from .const import (
    DOMAIN,
    MAX_RETRIES,
    RETRY_DELAY,
    COMMAND_TIMEOUT,
    UPDATE_TIMEOUT,
    MIN_UPDATE_INTERVAL,
    MIN_COMMAND_INTERVAL,
    API_ENDPOINT_MAIN,
    API_ENDPOINT_EVENT,
    CMD_EVSE_ENABLED,
    CMD_ONE_CHARGE,
    CMD_RESET_COUNTER,
)

_LOGGER = logging.getLogger(__name__)

class BaseEveusSwitch(SwitchEntity):
    """Base class for Eveus switches."""

    _attr_has_entity_name: Final = True
    _attr_should_poll: Final = True

    def __init__(self, host: str, username: str, password: str) -> None:
        """Initialize the switch."""
        self._host = host
        self._username = username
        self._password = password
        self._available = True
        self._session = None
        self._is_on = False
        self._command_lock = asyncio.Lock()
        self._update_lock = asyncio.Lock()
        self._last_command_time = 0
        self._last_update = time.time()
        self._state_data = {}
        self._error_count = 0
        self._max_errors = 3
        self._current_retry_delay = RETRY_DELAY

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self._host}_{self.name}"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._available

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._is_on

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._host)},
            "name": "Eveus EV Charger",
            "manufacturer": "Eveus",
            "model": f"Eveus ({self._host})",
            "configuration_url": f"http://{self._host}",
            "suggested_area": "Garage",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create client session with proper configuration."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=COMMAND_TIMEOUT)
            connector = aiohttp.TCPConnector(
                limit=1,
                force_close=True,
                enable_cleanup_closed=True
            )
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                raise_for_status=True
            )
        return self._session

    async def _send_command(
        self, 
        command: str, 
        value: int, 
        verify_command: bool = True
    ) -> bool:
        """Send command with improved retry logic and rate limiting."""
        current_time = time.time()
        if current_time - self._last_command_time < MIN_COMMAND_INTERVAL:
            await asyncio.sleep(MIN_COMMAND_INTERVAL)

        async with self._command_lock:
            for attempt in range(MAX_RETRIES):
                try:
                    session = await self._get_session()
                    async with session.post(
                        f"http://{self._host}{API_ENDPOINT_EVENT}",
                        auth=aiohttp.BasicAuth(self._username, self._password),
                        headers={"Content-type": "application/x-www-form-urlencoded"},
                        data=f"pageevent={command}&{command}={value}",
                        timeout=COMMAND_TIMEOUT,
                    ) as response:
                        if "error" in (await response.text()).lower():
                            raise ValueError(f"Error response for command {command}")

                        if verify_command:
                            async with session.post(
                                f"http://{self._host}{API_ENDPOINT_MAIN}",
                                auth=aiohttp.BasicAuth(self._username, self._password),
                                timeout=COMMAND_TIMEOUT,
                            ) as verify_response:
                                verify_data = await verify_response.json()
                                if not self._validate_command_response(
                                    verify_data, 
                                    command, 
                                    value
                                ):
                                    raise ValueError(
                                        f"Command verification failed for {command}"
                                    )

                        self._available = True
                        self._last_command_time = current_time
                        self._error_count = 0
                        self._current_retry_delay = RETRY_DELAY
                        return True

                except aiohttp.ClientError as err:
                    if attempt + 1 >= MAX_RETRIES:
                        self._error_count += 1
                        self._available = self._error_count < self._max_errors
                        _LOGGER.error(
                            "Network error sending command %s: %s",
                            command,
                            str(err)
                        )
                        return False
                    await asyncio.sleep(self._current_retry_delay)
                    self._current_retry_delay = min(self._current_retry_delay * 2, 60)
                
                except Exception as err:
                    if attempt + 1 >= MAX_RETRIES:
                        self._error_count += 1
                        self._available = self._error_count < self._max_errors
                        _LOGGER.error(
                            "Error sending command %s: %s",
                            command,
                            str(err)
                        )
                        return False
                    await asyncio.sleep(self._current_retry_delay)
                    self._current_retry_delay = min(self._current_retry_delay * 2, 60)

            return False

    def _validate_command_response(
        self, 
        response_data: dict, 
        command: str, 
        value: int
    ) -> bool:
        """Validate command response data."""
        if not isinstance(response_data, dict):
            return False

        try:
            if command == CMD_EVSE_ENABLED:
                return response_data.get("evseEnabled") == value
            elif command == CMD_ONE_CHARGE:
                return response_data.get("oneCharge") == value
            elif command == CMD_RESET_COUNTER:
                return True  # Reset commands don't need validation
        except Exception as err:
            _LOGGER.debug(
                "Validation error for command %s: %s", 
                command, 
                str(err)
            )
            return False

        return False

    async def async_update(self) -> None:
        """Update device state with retries and backoff."""
        if time.time() - self._last_update < MIN_UPDATE_INTERVAL:
            return

        async with self._update_lock:
            for attempt in range(MAX_RETRIES):
                try:
                    session = await self._get_session()
                    async with session.post(
                        f"http://{self._host}{API_ENDPOINT_MAIN}",
                        auth=aiohttp.BasicAuth(self._username, self._password),
                        timeout=UPDATE_TIMEOUT,
                    ) as response:
                        self._state_data = await response.json()
                        self._available = True
                        self._error_count = 0
                        self._current_retry_delay = RETRY_DELAY
                        self._last_update = time.time()
                        return

                except Exception as err:
                    if attempt + 1 >= MAX_RETRIES:
                        self._error_count += 1
                        self._available = self._error_count < self._max_errors
                        _LOGGER.error(
                            "Error updating state for %s: %s",
                            self.name,
                            str(err)
                        )
                        return
                    await asyncio.sleep(self._current_retry_delay)
                    self._current_retry_delay = min(self._current_retry_delay * 2, 60)

    async def async_will_remove_from_hass(self) -> None:
        """Clean up resources when entity is removed."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

class EveusStopChargingSwitch(BaseEveusSwitch):
    """Representation of Eveus charging control switch."""

    _attr_name = "Stop Charging"
    _attr_icon = "mdi:ev-station"
    _attr_entity_category = EntityCategory.CONFIG

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on charging."""
        if await self._send_command(CMD_EVSE_ENABLED, 1):
            self._is_on = True

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off charging."""
        if await self._send_command(CMD_EVSE_ENABLED, 0):
            self._is_on = False

    async def async_update(self) -> None:
        """Update state."""
        await super().async_update()
        if self._available and "evseEnabled" in self._state_data:
            self._is_on = self._state_data["evseEnabled"] == 1

class EveusOneChargeSwitch(BaseEveusSwitch):
    """Representation of Eveus one charge switch."""

    _attr_name = "One Charge"
    _attr_icon = "mdi:lightning-bolt"
    _attr_entity_category = EntityCategory.CONFIG

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable one charge mode."""
        if await self._send_command(CMD_ONE_CHARGE, 1):
            self._is_on = True

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable one charge mode."""
        if await self._send_command(CMD_ONE_CHARGE, 0):
            self._is_on = False

    async def async_update(self) -> None:
        """Update state."""
        await super().async_update()
        if self._available and "oneCharge" in self._state_data:
            self._is_on = self._state_data["oneCharge"] == 1

class EveusResetCounterASwitch(BaseEveusSwitch):
    """Representation of Eveus reset counter A switch."""

    _attr_name = "Reset Counter A"
    _attr_icon = "mdi:counter"
    _attr_entity_category = EntityCategory.CONFIG

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Reset counter A."""
        await self._send_command(CMD_RESET_COUNTER, 0, verify_command=False)
        self._is_on = False

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Reset command for off state."""
        await self._send_command(CMD_RESET_COUNTER, 0, verify_command=False)
        self._is_on = False

    async def async_update(self) -> None:
        """Update state."""
        await super().async_update()
        if self._available:
            try:
                iem1_value = self._state_data.get("IEM1")
                if iem1_value in (None, "null", "", "undefined", "ERROR"):
                    self._is_on = False
                else:
                    # Convert to float and check if non-zero
                    self._is_on = float(iem1_value) != 0
            except (TypeError, ValueError):
                self._is_on = False

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eveus switches based on config entry."""
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    switches = [
        EveusStopChargingSwitch(host, username, password),
        EveusOneChargeSwitch(host, username, password),
        EveusResetCounterASwitch(host, username, password),
    ]

    # Store entity references
    if "entities" not in hass.data[DOMAIN][entry.entry_id]:
        hass.data[DOMAIN][entry.entry_id]["entities"] = {}

    hass.data[DOMAIN][entry.entry_id]["entities"]["switch"] = {
        switch.unique_id: switch for switch in switches
    }

    async_add_entities(switches)
