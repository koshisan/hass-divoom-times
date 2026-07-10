from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

CLOUD_BASE = "https://app.divoom-gz.com"

# Cloud command endpoints — POST to CLOUD_BASE + path with the full command JSON.
CLOUD_LOGIN = "/UserLogin"
CLOUD_DEVICE_LIST = "/Device/GetList"
CLOUD_LAN_DISCOVERY = "/Device/ReturnSameLANDevice"


class DivoomError(Exception):
    """Base error."""


class DivoomAuthError(DivoomError):
    """UserId/Token was refused by the cloud, or DeviceToken by a local device."""


class DivoomCommandError(DivoomError):
    """Cloud accepted the request but returned a non-zero ReturnCode."""


class DivoomConnectionError(DivoomError):
    """Network error reaching the cloud or device."""


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
    device_type: int  # a.k.a. Hardware in ReturnSameLANDevice
    device_version: int
    private_ip: str
    mac: str
    online: bool


def _password_md5(password: str) -> str:
    return hashlib.md5(password.encode("utf-8")).hexdigest()


class DivoomCloudClient:
    """Talks to Divoom's cloud on behalf of one signed-in user.

    Sessions are cheap — one instance per config entry.
    """

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

    def set_credentials(self, user_id: int, token: int) -> None:
        self._user_id = user_id
        self._token = token

    async def login(self, email: str, password: str) -> dict[str, Any]:
        body = {"Email": email, "Password": _password_md5(password)}
        data = await self._post_raw(CLOUD_LOGIN, body)
        if data.get("ReturnCode") != 0:
            raise DivoomAuthError(data.get("ReturnMessage") or "login failed")
        self._user_id = int(data["UserId"])
        self._token = int(data["Token"])
        return data

    async def list_devices(self) -> list[OwnedDevice]:
        data = await self._post_authed(CLOUD_DEVICE_LIST, {})
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

    async def discover_lan_devices(self) -> list[LanDevice]:
        """Unauthenticated discovery — cloud matches by public IP."""
        data = await self._post_raw(CLOUD_LAN_DISCOVERY, {})
        if data.get("ReturnCode") != 0:
            raise DivoomError(f"cloud discovery failed: {data!r}")
        out: list[LanDevice] = []
        for entry in data.get("DeviceList", []) or []:
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

    async def send_command(
        self, command: str, device_id: int, extra: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"DeviceId": device_id}
        if extra:
            body.update(extra)
        return await self._post_authed(f"/{command}", body)

    async def _post_authed(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if self._user_id is None or self._token is None:
            raise DivoomAuthError("not signed in")
        full: dict[str, Any] = {"UserId": self._user_id, "Token": self._token}
        full.update(body)
        data = await self._post_raw(path, full)
        rc = data.get("ReturnCode")
        if rc == 0 or rc is None:
            return data
        # 3 = "Request data is incomplete" — surface as command error, not auth
        raise DivoomCommandError(
            f"{path} returned code {rc}: {data.get('ReturnMessage', '')}"
        )

    async def _post_raw(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{CLOUD_BASE}{path}"
        try:
            async with self._session.post(
                url, json=body, timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise DivoomConnectionError(str(err)) from err
