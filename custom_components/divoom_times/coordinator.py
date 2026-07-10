from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DivoomAuthError, DivoomConnectionError, DivoomLocalClient
from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_TOKEN,
    CONF_HOST,
    CONF_PORT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class DivoomCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.data.get(CONF_HOST)}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        session = async_get_clientsession(hass)
        self.client = DivoomLocalClient(
            session=session,
            host=entry.data[CONF_HOST],
            device_id=entry.data.get(CONF_DEVICE_ID),
            device_token=entry.data.get(CONF_DEVICE_TOKEN),
            port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        )
        self.entry = entry

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.get_all_conf()
        except DivoomAuthError as err:
            raise UpdateFailed(f"auth: {err}") from err
        except DivoomConnectionError as err:
            raise UpdateFailed(f"connection: {err}") from err
