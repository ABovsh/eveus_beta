"""Common functionality for Eveus integration."""
from __future__ import annotations

import logging
import aiohttp
import asyncio
from typing import Any

from homeassistant.helpers import aiohttp_client
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

class EveusUpdater:
    """Data updater for Eveus device."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        username: str,
        password: str,
    ) -> None:
        self.hass = hass
        self.host = host
        self.username = username
        self.password = password
        self.data = {}
        self._session = aiohttp_client.async_get_clientsession(hass)
        self._unsub_update = None

    async def async_init(self):
        """Initialize the updater."""
        await self.async_update()
        self._schedule_update()

    def _schedule_update(self):
        """Schedule the next update."""
        self._unsub_update = self.hass.helpers.event.async_call_later(
            30, self.async_update
        )

    async def async_update(self, _=None):
        """Fetch latest data from device."""
        try:
            async with async_timeout.timeout(10):
                response = await self._session.get(
                    f"http://{self.host}/status",
                    auth=aiohttp.BasicAuth(self.username, self.password)
                )
                response.raise_for_status()
                self.data = await response.json()
        except Exception as err:
            _LOGGER.warning("Error updating Eveus data: %s", err)
        finally:
            self._schedule_update()

    async def async_shutdown(self):
        """Shutdown the updater."""
        if self._unsub_update:
            self._unsub_update()

# Add missing function that platforms are trying to import
async def send_eveus_command(
    hass: HomeAssistant,
    host: str,
    username: str,
    password: str,
    command: str,
    value: Any
) -> bool:
    """Send command to Eveus device."""
    try:
        session = aiohttp_client.async_get_clientsession(hass)
        async with async_timeout.timeout(10):
            response = await session.post(
                f"http://{host}/control",
                auth=aiohttp.BasicAuth(username, password),
                json={command: value}
            )
            response.raise_for_status()
            return True
    except Exception as err:
        _LOGGER.error("Error sending command: %s", err)
        return False
