from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import (
    CLOUD_ENDPOINT_DEVICE_LIST,
    CLOUD_ENDPOINT_LAN_DEVICES,
    CLOUD_ENDPOINT_USER_LOGIN,
    CMD_GET_ALL_CONF,
    CMD_ON_OFF_SCREEN,
    CMD_SET_BRIGHTNESS,
    CMD_SET_INDEX,
    DEFAULT_PORT,
    DEVICE_ENDPOINT_POST,
    DIVOOM_CLOUD_BASE,
)

_LOGGER = logging.getLogger(__name__)


class DivoomError(Exception):
    """Base error for the Divoom API."""


class DivoomAuthError(DivoomError):
    """Raised when the device rejects the request due to a bad or missing DeviceToken."""


class DivoomConnectionError(DivoomError):
    """Raised when we cannot reach the device."""


@dataclass(slots=True)
class LanDevice:
    device_id: int
    device_name: str
    ip: str
    mac: str
    hardware: int


async def cloud_discover_lan_devices(session: aiohttp.ClientSession) -> list[LanDevice]:
    """Ask the Divoom cloud which of the caller's LAN peers are Divoom devices.

    Works without auth as long as the caller's public IP matches the devices'.
    """
    url = f"{DIVOOM_CLOUD_BASE}{CLOUD_ENDPOINT_LAN_DEVICES}"
    async with session.post(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
        resp.raise_for_status()
        payload = await resp.json(content_type=None)
    if payload.get("ReturnCode") != 0:
        raise DivoomError(f"cloud discovery failed: {payload!r}")
    out: list[LanDevice] = []
    for entry in payload.get("DeviceList", []) or []:
        out.append(
            LanDevice(
                device_id=int(entry["DeviceId"]),
                device_name=str(entry.get("DeviceName") or ""),
                ip=str(entry["DevicePrivateIP"]),
                mac=str(entry.get("DeviceMac") or ""),
                hardware=int(entry.get("Hardware") or 0),
            )
        )
    return out


async def cloud_login(
    session: aiohttp.ClientSession, email: str, password_md5: str
) -> dict[str, Any]:
    """POST /UserLogin. `password_md5` must be the lowercase hex md5 of the password."""
    url = f"{DIVOOM_CLOUD_BASE}{CLOUD_ENDPOINT_USER_LOGIN}"
    body = {"Email": email, "Password": password_md5}
    async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        resp.raise_for_status()
        return await resp.json(content_type=None)


async def cloud_device_list(
    session: aiohttp.ClientSession, user_id: int, token: str
) -> dict[str, Any]:
    """POST /Device/ReturnDeviceList — the user's owned devices with per-device tokens."""
    url = f"{DIVOOM_CLOUD_BASE}{CLOUD_ENDPOINT_DEVICE_LIST}"
    body = {"UserId": user_id, "Token": token}
    async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        resp.raise_for_status()
        return await resp.json(content_type=None)


class DivoomLocalClient:
    """Talks to a Times Gate / Times Frame over HTTP on port 80.

    Newer firmware requires DeviceId + DeviceToken on most commands.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        device_id: int | None = None,
        device_token: str | None = None,
        port: int = DEFAULT_PORT,
        timeout: float = 5.0,
    ) -> None:
        self._session = session
        self._host = host
        self._port = port
        self._device_id = device_id
        self._device_token = device_token
        self._timeout = timeout

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}{DEVICE_ENDPOINT_POST}"

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = dict(payload)
        if self._device_id is not None:
            body.setdefault("DeviceId", self._device_id)
        if self._device_token is not None:
            body.setdefault("DeviceToken", self._device_token)
        try:
            async with self._session.post(
                self.url, json=body, timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise DivoomConnectionError(str(err)) from err
        err_code = data.get("error_code")
        if isinstance(err_code, str) and "DeviceToken" in err_code:
            raise DivoomAuthError(err_code)
        return data

    async def get_all_conf(self) -> dict[str, Any]:
        return await self._post({"Command": CMD_GET_ALL_CONF})

    async def set_brightness(self, brightness: int) -> None:
        brightness = max(0, min(100, int(brightness)))
        await self._post({"Command": CMD_SET_BRIGHTNESS, "Brightness": brightness})

    async def set_screen_on(self, on: bool) -> None:
        await self._post({"Command": CMD_ON_OFF_SCREEN, "OnOff": 1 if on else 0})

    async def set_channel(self, index: int) -> None:
        await self._post({"Command": CMD_SET_INDEX, "SelectIndex": int(index)})
