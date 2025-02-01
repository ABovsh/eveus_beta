"""Eveus API client."""
import logging
import asyncio
from typing import Any, Optional
import aiohttp

from .exceptions import CannotConnect, InvalidAuth, CommandError, TimeoutError
from .models import DeviceInfo, DeviceState

_LOGGER = logging.getLogger(__name__)

class EveusClient:
    """API client for Eveus EV charger."""

    def __init__(self, device_info: DeviceInfo) -> None:
        """Initialize the client."""
        self._device_info = device_info
        self._session: Optional[aiohttp.ClientSession] = None
        self._command_lock = asyncio.Lock()
        self.state: Optional[DeviceState] = None
        self._available = True
        self._error_count = 0
        self._max_errors = 3
        self._last_update = 0

    @property
    def available(self) -> bool:
        """Return if device is available."""
        return self._available

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create client session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            connector = aiohttp.TCPConnector(limit=1, force_close=True)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                auth=aiohttp.BasicAuth(
                    self._device_info.username,
                    self._device_info.password
                )
            )
        return self._session

    async def update(self) -> None:
        """Update device state."""
        try:
            session = await self._get_session()
            async with session.post(
                f"http://{self._device_info.host}/main",
                timeout=10
            ) as response:
                response.raise_for_status()
                data = await response.json()
                self.state = DeviceState.from_dict(data)
                self._available = True
                self._error_count = 0

        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                raise InvalidAuth from err
            raise CannotConnect from err
        except asyncio.TimeoutError as err:
            raise TimeoutError from err
        except Exception as err:
            self._error_count += 1
            self._available = self._error_count < self._max_errors
            raise CommandError(f"Error updating state: {err}") from err

    async def send_command(self, command: str, value: Any) -> None:
        """Send command to device."""
        async with self._command_lock:
            try:
                session = await self._get_session()
                async with session.post(
                    f"http://{self._device_info.host}/pageEvent",
                    headers={"Content-type": "application/x-www-form-urlencoded"},
                    data=f"pageevent={command}&{command}={value}",
                    timeout=10
                ) as response:
                    response.raise_for_status()
                    
                # Verify command execution
                await self.update()
                
            except Exception as err:
                raise CommandError(f"Error sending command {command}: {err}") from err

    async def close(self) -> None:
        """Close the client."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
