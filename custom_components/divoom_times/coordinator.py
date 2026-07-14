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
    CMD_GET_ON_OFF_SCREEN,
    CMD_ON_OFF_SCREEN,
    CMD_SET_RGB_INFO,
    CONF_DEVICE_ID,
    CONF_DEVICE_TYPE,
    CONF_HOST,
    CONF_LOCAL_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    GETALLCONF_HAS_STATE,
    HTTP_PROFILES,
)

_LOGGER = logging.getLogger(__name__)

# Keys we copy from responses into the coordinator's data dict.
_STATE_KEYS = (
    "Brightness",
    "LightSwitch",
    "MirrorFlag",
    "TemperatureMode",
    "Time24Flag",
    "DateFormat",
    "OnOff",
    "_SelectIndex",
)


class DivoomCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.data.get(CONF_DEVICE_ID)}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        session = async_get_clientsession(hass)
        device_type = entry.data[CONF_DEVICE_TYPE]
        profile = HTTP_PROFILES[device_type]
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
        self._device_type: int = device_type
        # Times Gate's GetAllConf carries the full state; Times Frame's
        # returns just an ack, so we poll a different command there and
        # bookkeep Brightness locally.
        self._uses_get_all_conf = device_type in GETALLCONF_HAS_STATE

    async def async_send(
        self, command: str, extra: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            resp = await self.transport.send(command, extra)
        except DivoomAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        # Divoom firmware quirk: Channel/SetRGBInfo silently turns the
        # screen (LightSwitch) ON regardless of the payload's OnOff. If
        # the user had the screen off, restore it right after the RGB
        # command lands.
        if command == CMD_SET_RGB_INFO:
            desired = (self.data or {}).get("LightSwitch")
            if isinstance(desired, int) and desired == 0:
                try:
                    await self.transport.send(CMD_ON_OFF_SCREEN, {"OnOff": 0})
                except (DivoomAuthError, DivoomConnectionError, DivoomCommandError):
                    pass
        # Some devices echo the just-set value back — capture it before
        # the next poll so the UI doesn't stall on a stale reading.
        self._merge_state_fields(resp)
        await self.async_request_refresh()
        return resp

    async def _async_update_data(self) -> dict[str, Any]:
        cmd = CMD_GET_ALL_CONF if self._uses_get_all_conf else CMD_GET_ON_OFF_SCREEN
        try:
            resp = await self.transport.send(cmd)
        except DivoomAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DivoomConnectionError as err:
            raise UpdateFailed(f"connection: {err}") from err
        except DivoomCommandError as err:
            _LOGGER.debug("%s refused: %s", cmd, err)
            return self.data or {}
        merged = dict(self.data or {})
        self._apply_state(merged, resp)
        return merged

    def _merge_state_fields(self, resp: dict[str, Any]) -> None:
        if not resp:
            return
        current = dict(self.data or {})
        self._apply_state(current, resp)
        self.async_set_updated_data(current)

    def _apply_state(self, target: dict[str, Any], resp: dict[str, Any]) -> None:
        for key in _STATE_KEYS:
            if key in resp:
                target[key] = resp[key]
        # Normalise OnOff -> LightSwitch so entities have one place to look.
        if "OnOff" in resp and "LightSwitch" not in resp:
            target["LightSwitch"] = int(resp["OnOff"])
