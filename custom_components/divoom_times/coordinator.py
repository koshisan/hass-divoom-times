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
    CloudTransport,
    DivoomAuthError,
    DivoomCommandError,
    DivoomConnectionError,
    DivoomTransport,
    LocalTransport,
)
from .const import (
    CMD_GET_ALL_CONF,
    CONF_DEVICE_ID,
    CONF_DEVICE_TYPE,
    CONF_HOST,
    CONF_LOCAL_TOKEN,
    CONF_TOKEN,
    CONF_TRANSPORT,
    CONF_USER_ID,
    DEFAULT_SCAN_INTERVAL_CLOUD,
    DEFAULT_SCAN_INTERVAL_LOCAL,
    DOMAIN,
    LOCAL_PROFILES,
    TRANSPORT_LOCAL,
)

_LOGGER = logging.getLogger(__name__)


def _build_transport(hass: HomeAssistant, entry: ConfigEntry) -> DivoomTransport:
    session = async_get_clientsession(hass)
    if entry.data[CONF_TRANSPORT] == TRANSPORT_LOCAL:
        profile = LOCAL_PROFILES[entry.data[CONF_DEVICE_TYPE]]
        return LocalTransport(
            session=session,
            host=entry.data[CONF_HOST],
            port=profile.port,
            path=profile.path,
            method=profile.method,
            local_token=entry.data.get(CONF_LOCAL_TOKEN),
        )
    return CloudTransport(
        session=session,
        user_id=entry.data[CONF_USER_ID],
        token=entry.data[CONF_TOKEN],
        device_id=entry.data[CONF_DEVICE_ID],
    )


class DivoomCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        interval = (
            DEFAULT_SCAN_INTERVAL_LOCAL
            if entry.data[CONF_TRANSPORT] == TRANSPORT_LOCAL
            else DEFAULT_SCAN_INTERVAL_CLOUD
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.data.get(CONF_DEVICE_ID)}",
            update_interval=timedelta(seconds=interval),
        )
        self.transport = _build_transport(hass, entry)
        self.entry = entry
        self._last_brightness: int | None = None
        self._is_on: bool = True

    @property
    def last_brightness(self) -> int | None:
        return self._last_brightness

    @property
    def is_on(self) -> bool:
        return self._is_on

    def record_brightness(self, brightness_pct: int) -> None:
        self._last_brightness = brightness_pct
        if brightness_pct > 0:
            self._is_on = True

    def record_on_off(self, on: bool) -> None:
        self._is_on = on

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            resp = await self.transport.send(CMD_GET_ALL_CONF)
        except DivoomAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DivoomConnectionError as err:
            raise UpdateFailed(f"connection: {err}") from err
        except DivoomCommandError as err:
            _LOGGER.debug("GetAllConf not supported: %s", err)
            return {}
        b = resp.get("Brightness")
        if isinstance(b, int):
            self._last_brightness = b
        if isinstance(resp.get("LightSwitch"), int):
            self._is_on = bool(resp["LightSwitch"])
        return resp
