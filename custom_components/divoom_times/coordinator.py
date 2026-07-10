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
    DivoomCloudClient,
    DivoomCommandError,
    DivoomConnectionError,
)
from .const import (
    CMD_GET_INDEX,
    CONF_DEVICE_ID,
    CONF_TOKEN,
    CONF_USER_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
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
        self.client = DivoomCloudClient(
            session=session,
            user_id=entry.data[CONF_USER_ID],
            token=entry.data[CONF_TOKEN],
        )
        self.device_id: int = entry.data[CONF_DEVICE_ID]
        self.entry = entry
        # Optimistic light state — cloud has no read-back for brightness
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
            resp = await self.client.send_command(CMD_GET_INDEX, self.device_id)
        except DivoomAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DivoomConnectionError as err:
            raise UpdateFailed(f"connection: {err}") from err
        except DivoomCommandError as err:
            # Some devices refuse GetIndex with the minimal payload — non-fatal.
            _LOGGER.debug("GetIndex not supported for %s: %s", self.device_id, err)
            return {}
        return resp
