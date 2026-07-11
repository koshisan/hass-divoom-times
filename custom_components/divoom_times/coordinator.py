from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    DivoomAuthError,
    DivoomCommandError,
    DivoomConnectionError,
    HttpTransport,
)
from .const import (
    CMD_GET_ALL_CONF,
    CONF_DEVICE_ID,
    CONF_DEVICE_TYPE,
    CONF_HOST,
    CONF_LOCAL_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HTTP_PROFILES,
)

_LOGGER = logging.getLogger(__name__)


class DivoomCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.data.get(CONF_DEVICE_ID)}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        session = async_get_clientsession(hass)
        profile = HTTP_PROFILES[entry.data[CONF_DEVICE_TYPE]]
        self.transport = HttpTransport(
            session=session,
            host=entry.data[CONF_HOST],
            port=profile.port,
            path=profile.path,
            method=profile.method,
            local_token=entry.data[CONF_LOCAL_TOKEN],
        )
        self.entry = entry
        self.device_id: int = entry.data[CONF_DEVICE_ID]

    async def async_send(
        self, command: str, extra: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            resp = await self.transport.send(command, extra)
        except DivoomAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        await self.async_request_refresh()
        return resp

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.transport.send(CMD_GET_ALL_CONF)
        except DivoomAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DivoomConnectionError as err:
            raise UpdateFailed(f"connection: {err}") from err
        except DivoomCommandError as err:
            _LOGGER.debug("GetAllConf refused: %s", err)
            return self.data or {}
