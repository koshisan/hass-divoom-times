from __future__ import annotations

import logging
import time
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
    DivoomError,
    HttpTransport,
)
from .const import (
    CMD_GET_ALL_CONF,
    CMD_GET_ON_OFF_SCREEN,
    CMD_ON_OFF_SCREEN,
    CMD_SET_RGB_INFO,
    CONF_CLOUD_TOKEN,
    CONF_DEVICE_ID,
    CONF_DEVICE_TYPE,
    CONF_HOST,
    CONF_LOCAL_TOKEN,
    CONF_USER_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    GETALLCONF_HAS_STATE,
    HTTP_PROFILES,
)

# After this many consecutive connection failures, ask the Divoom cloud
# whether the device's LAN IP has changed. Threshold + cooldown keeps us
# from hammering appin.divoom-gz.com when a device is genuinely offline.
IP_REFRESH_MIN_FAILURES = 3
IP_REFRESH_COOLDOWN = 120.0

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
        self._consecutive_failures = 0
        self._last_ip_refresh_attempt = 0.0

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
            self._consecutive_failures += 1
            if self._consecutive_failures >= IP_REFRESH_MIN_FAILURES:
                try:
                    await self._maybe_refresh_ip_from_cloud()
                except DivoomAuthError as auth_err:
                    raise ConfigEntryAuthFailed(str(auth_err)) from auth_err
            raise UpdateFailed(f"connection: {err}") from err
        except DivoomCommandError as err:
            _LOGGER.debug("%s refused: %s", cmd, err)
            return self.data or {}
        self._consecutive_failures = 0
        merged = dict(self.data or {})
        self._apply_state(merged, resp)
        return merged

    async def _maybe_refresh_ip_from_cloud(self) -> None:
        # DHCP hands the device a new IP → LAN transport dies silently.
        # Ask Divoom's cloud (which the device checks in to) for the
        # current DevicePrivateIP and patch the config entry in place.
        now = time.monotonic()
        if now - self._last_ip_refresh_attempt < IP_REFRESH_COOLDOWN:
            return
        self._last_ip_refresh_attempt = now

        user_id = self.entry.data.get(CONF_USER_ID)
        cloud_token = self.entry.data.get(CONF_CLOUD_TOKEN)
        if user_id is None or cloud_token is None:
            _LOGGER.debug(
                "no stored cloud creds for %s, cannot auto-recover IP",
                self.device_id,
            )
            return

        session = async_get_clientsession(self.hass)
        cloud = DivoomCloudClient(session, user_id=int(user_id), token=int(cloud_token))
        try:
            devices = await cloud.list_devices()
        except DivoomAuthError:
            _LOGGER.info(
                "cloud token expired for device %s, triggering reauth",
                self.device_id,
            )
            raise
        except DivoomError as err:
            _LOGGER.warning("cloud IP refresh failed: %s", err)
            return

        match = next((d for d in devices if d.device_id == self.device_id), None)
        if match is None:
            _LOGGER.warning(
                "device %s no longer in cloud device list", self.device_id
            )
            return
        new_ip = match.private_ip
        if not new_ip:
            _LOGGER.info(
                "cloud has no IP for device %s (device offline?)", self.device_id
            )
            return
        current_ip = self.entry.data.get(CONF_HOST)
        if new_ip == current_ip:
            _LOGGER.debug(
                "cloud IP %s matches stored — device down for another reason",
                new_ip,
            )
            return

        _LOGGER.info(
            "device %s LAN IP moved %s → %s, patching config entry",
            self.device_id, current_ip, new_ip,
        )
        new_data = {**self.entry.data, CONF_HOST: new_ip}
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        profile = HTTP_PROFILES[self._device_type]
        self.transport = HttpTransport(
            session=session,
            host=new_ip,
            port=profile.port,
            path=profile.path,
            method=profile.method,
            local_token=self.entry.data[CONF_LOCAL_TOKEN],
        )
        # Reset so the next successful poll doesn't hit the cooldown for
        # nothing; the caller still raises UpdateFailed for this cycle.
        self._consecutive_failures = 0

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
