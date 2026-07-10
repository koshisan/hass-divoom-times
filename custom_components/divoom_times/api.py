from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

CLOUD_BASE = "https://app.divoom-gz.com"
CLOUD_LOGIN = "/UserLogin"
CLOUD_DEVICE_LIST = "/Device/GetList"
CLOUD_LAN_DISCOVERY = "/Device/ReturnSameLANDevice"


class DivoomError(Exception):
    """Base error."""


class DivoomAuthError(DivoomError):
    """Rejected credentials — cloud login or local token."""


class DivoomCommandError(DivoomError):
    """Non-zero ReturnCode from a valid endpoint."""


class DivoomConnectionError(DivoomError):
    """Network error."""


@dataclass(slots=True)
class LanDevice:
    device_id: int
    device_name: str
    ip: str
    mac: str
    hardware: int


@dataclass(slots=True)
class OwnedDevice:
    device_id: int
    device_name: str
    device_type: int
    device_version: int
    private_ip: str
    mac: str
    online: bool


def _password_md5(password: str) -> str:
    return hashlib.md5(password.encode("utf-8")).hexdigest()


class DivoomTransport(ABC):
    """Abstract command transport for a single device."""

    @abstractmethod
    async def send(
        self, command: str, extra: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        ...


class LocalTransport(DivoomTransport):
    """Local HTTP transport with per-device profile.

    Times Frame (HW 510): GET  /divoom_api on port 9000, no token.
    Times Gate HW 400   : POST /post        on port 80,   requires LocalToken.
    Times Gate HW 402   : POST /divoom_api  on port 9000, requires LocalToken.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        path: str,
        method: str,
        local_token: int | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._session = session
        self._host = host
        self._port = port
        self._path = path
        self._method = method
        self._local_token = local_token
        self._timeout = timeout

    async def send(
        self, command: str, extra: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"Command": command}
        if self._local_token is not None:
            body["LocalToken"] = self._local_token
        if extra:
            body.update(extra)
        url = f"http://{self._host}:{self._port}{self._path}"
        try:
            async with self._session.request(
                self._method,
                url,
                json=body,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise DivoomConnectionError(str(err)) from err
        # Older firmware returns error_code as string, newer as ReturnCode int.
        ec = data.get("error_code")
        rc = data.get("ReturnCode")
        if isinstance(ec, str) and "Token" in ec:
            raise DivoomAuthError(ec)
        if rc not in (None, 0):
            raise DivoomCommandError(
                f"{command}: rc={rc} {data.get('ReturnMessage', '')}"
            )
        if isinstance(ec, str) and ec not in ("", "0"):
            raise DivoomCommandError(f"{command}: {ec}")
        return data


class CloudTransport(DivoomTransport):
    """Cloud relay — works for any signed-in device without a LocalToken."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        user_id: int,
        token: int,
        device_id: int,
        timeout: float = 8.0,
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._token = token
        self._device_id = device_id
        self._timeout = timeout

    async def send(
        self, command: str, extra: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "UserId": self._user_id,
            "Token": self._token,
            "DeviceId": self._device_id,
        }
        if extra:
            body.update(extra)
        url = f"{CLOUD_BASE}/{command}"
        try:
            async with self._session.post(
                url, json=body, timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise DivoomConnectionError(str(err)) from err
        rc = data.get("ReturnCode")
        if rc not in (None, 0):
            raise DivoomCommandError(
                f"{command}: rc={rc} {data.get('ReturnMessage', '')}"
            )
        return data


class DivoomCloudClient:
    """Login, discovery, and device listing against app.divoom-gz.com."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        user_id: int | None = None,
        token: int | None = None,
        timeout: float = 8.0,
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._token = token
        self._timeout = timeout

    @property
    def user_id(self) -> int | None:
        return self._user_id

    @property
    def token(self) -> int | None:
        return self._token

    async def login(self, email: str, password: str) -> dict[str, Any]:
        body = {"Email": email, "Password": _password_md5(password)}
        data = await self._post(CLOUD_LOGIN, body)
        if data.get("ReturnCode") != 0:
            raise DivoomAuthError(data.get("ReturnMessage") or "login failed")
        self._user_id = int(data["UserId"])
        self._token = int(data["Token"])
        return data

    async def list_devices(self) -> list[OwnedDevice]:
        if self._user_id is None or self._token is None:
            raise DivoomAuthError("not signed in")
        data = await self._post(
            CLOUD_DEVICE_LIST, {"UserId": self._user_id, "Token": self._token}
        )
        out: list[OwnedDevice] = []
        for entry in data.get("DeviceList", []) or []:
            out.append(
                OwnedDevice(
                    device_id=int(entry["DeviceId"]),
                    device_name=str(entry.get("DeviceName") or ""),
                    device_type=int(entry.get("DeviceType") or 0),
                    device_version=int(entry.get("DeviceVersion") or 0),
                    private_ip=str(entry.get("DevicePrivateIP") or ""),
                    mac=str(entry.get("DeviceBlueTooth") or ""),
                    online=str(entry.get("Online") or "0") == "1",
                )
            )
        return out

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{CLOUD_BASE}{path}"
        try:
            async with self._session.post(
                url, json=body, timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise DivoomConnectionError(str(err)) from err
