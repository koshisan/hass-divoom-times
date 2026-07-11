from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

CLOUD_BASE = "https://appin.divoom-gz.com"


class DivoomError(Exception):
    """Base error."""


class DivoomAuthError(DivoomError):
    """Rejected credentials — cloud login or LocalToken."""


class DivoomCommandError(DivoomError):
    """Non-zero ReturnCode / error_code from a valid endpoint."""


class DivoomConnectionError(DivoomError):
    """Network error."""


@dataclass(slots=True)
class OwnedDevice:
    device_id: int
    device_name: str
    device_type: int
    device_version: int
    private_ip: str
    mac: str
    local_token: int


def _password_md5(password: str) -> str:
    return hashlib.md5(password.encode("utf-8")).hexdigest()


class DivoomCloudClient:
    """Login + device enumeration against appin.divoom-gz.com."""

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
        body = {
            "Email": email,
            "Password": _password_md5(password),
            "CountryISOCode": "US",
            "Language": "en",
            "TimeZone": "UTC",
        }
        data = await self._post("UserLogin", body)
        if data.get("ReturnCode") != 0:
            raise DivoomAuthError(data.get("ReturnMessage") or "login failed")
        self._user_id = int(data["UserId"])
        self._token = int(data["Token"])
        return data

    async def list_devices(self) -> list[OwnedDevice]:
        if self._user_id is None or self._token is None:
            raise DivoomAuthError("not signed in")
        data = await self._post(
            "Device/GetListV2",
            {"UserId": self._user_id, "Token": self._token, "DeviceId": 0},
        )
        rc = data.get("ReturnCode")
        if rc == 11:
            raise DivoomAuthError("cloud token no longer valid")
        if rc != 0:
            raise DivoomError(
                f"Device/GetListV2 failed: {rc} {data.get('ReturnMessage', '')}"
            )
        out: list[OwnedDevice] = []
        for entry in data.get("DeviceList", []) or []:
            if "LocalToken" not in entry:
                continue
            out.append(
                OwnedDevice(
                    device_id=int(entry["DeviceId"]),
                    device_name=str(entry.get("DeviceName") or ""),
                    device_type=int(entry.get("DeviceType") or 0),
                    device_version=int(entry.get("DeviceVersion") or 0),
                    private_ip=str(entry.get("DevicePrivateIP") or ""),
                    mac=str(entry.get("DeviceBlueTooth") or ""),
                    local_token=int(entry["LocalToken"]),
                )
            )
        return out

    async def _post(self, command: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{CLOUD_BASE}/{command}"
        payload = {"Command": command, **body}
        try:
            async with self._session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise DivoomConnectionError(str(err)) from err


class HttpTransport:
    """Per-device HTTP client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        path: str,
        method: str,
        local_token: int,
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
        body: dict[str, Any] = {"Command": command, "LocalToken": self._local_token}
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
        ec = data.get("error_code")
        rc = data.get("ReturnCode")
        if isinstance(ec, str) and "Token" in ec:
            raise DivoomAuthError(ec)
        if rc == 11 or rc == "11":
            raise DivoomAuthError(data.get("ReturnMessage") or "token rejected")
        if isinstance(rc, int) and rc != 0:
            raise DivoomCommandError(
                f"{command}: rc={rc} {data.get('ReturnMessage', '')}"
            )
        if isinstance(ec, str) and ec not in ("", "0"):
            raise DivoomCommandError(f"{command}: {ec}")
        return data
