from __future__ import annotations

import hashlib
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    DivoomAuthError,
    DivoomConnectionError,
    DivoomError,
    DivoomLocalClient,
    LanDevice,
    cloud_device_list,
    cloud_discover_lan_devices,
    cloud_login,
)
from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TOKEN,
    CONF_HARDWARE,
    CONF_HOST,
    CONF_MAC,
    CONF_PORT,
    DEFAULT_PORT,
    DOMAIN,
    HARDWARE_NAMES,
)

_LOGGER = logging.getLogger(__name__)


class DivoomTimesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: list[LanDevice] = []
        self._pending: LanDevice | None = None
        self._cloud_creds: tuple[int, str] | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is None:
            return self.async_show_menu(
                step_id="user",
                menu_options=["discover", "manual", "cloud"],
            )
        return await self.async_step_discover()

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if not self._discovered:
            session = async_get_clientsession(self.hass)
            try:
                self._discovered = await cloud_discover_lan_devices(session)
            except DivoomError as err:
                errors["base"] = "discovery_failed"
                _LOGGER.warning("LAN discovery failed: %s", err)

        if user_input is not None and "device_id" in user_input:
            chosen = next(
                (d for d in self._discovered if str(d.device_id) == user_input["device_id"]),
                None,
            )
            if chosen is None:
                errors["device_id"] = "unknown_device"
            else:
                self._pending = chosen
                if self._cloud_creds is not None:
                    return await self._finish_from_cloud()
                return await self.async_step_token()

        if not self._discovered and not errors:
            errors["base"] = "no_devices_found"

        options = {
            str(d.device_id): f"{d.device_name} ({d.ip}) — {HARDWARE_NAMES.get(d.hardware, f'HW{d.hardware}')}"
            for d in self._discovered
        }
        schema = vol.Schema(
            {vol.Required("device_id"): vol.In(options)}
            if options
            else {}
        )
        return self.async_show_form(step_id="discover", data_schema=schema, errors=errors)

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            unique = f"{user_input[CONF_HOST]}:{user_input.get(CONF_PORT, DEFAULT_PORT)}"
            await self.async_set_unique_id(unique)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input.get(CONF_DEVICE_NAME) or user_input[CONF_HOST],
                data=user_input,
            )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_DEVICE_ID): int,
                vol.Optional(CONF_DEVICE_TOKEN): str,
                vol.Optional(CONF_DEVICE_NAME): str,
            }
        )
        return self.async_show_form(step_id="manual", data_schema=schema, errors=errors)

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            pw_md5 = hashlib.md5(user_input["password"].encode()).hexdigest()
            try:
                resp = await cloud_login(session, user_input["email"], pw_md5)
            except Exception as err:  # noqa: BLE001
                errors["base"] = "login_failed"
                _LOGGER.warning("Divoom cloud login failed: %s", err)
            else:
                if resp.get("ReturnCode") != 0:
                    errors["base"] = "login_failed"
                else:
                    self._cloud_creds = (int(resp["UserId"]), str(resp["Token"]))
                    return await self.async_step_discover()

        schema = vol.Schema({vol.Required("email"): str, vol.Required("password"): str})
        return self.async_show_form(step_id="cloud", data_schema=schema, errors=errors)

    async def async_step_token(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        assert self._pending is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {
                CONF_HOST: self._pending.ip,
                CONF_PORT: DEFAULT_PORT,
                CONF_DEVICE_ID: self._pending.device_id,
                CONF_DEVICE_TOKEN: user_input[CONF_DEVICE_TOKEN],
                CONF_DEVICE_NAME: self._pending.device_name,
                CONF_MAC: self._pending.mac,
                CONF_HARDWARE: self._pending.hardware,
            }
            ok = await _verify(self.hass, data)
            if not ok:
                errors["base"] = "auth_failed"
            else:
                await self.async_set_unique_id(str(self._pending.device_id))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=self._pending.device_name or self._pending.ip, data=data
                )
        return self.async_show_form(
            step_id="token",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE_TOKEN): str}),
            description_placeholders={
                "name": self._pending.device_name,
                "ip": self._pending.ip,
            },
            errors=errors,
        )

    async def _finish_from_cloud(self) -> FlowResult:
        assert self._pending is not None and self._cloud_creds is not None
        user_id, token = self._cloud_creds
        session = async_get_clientsession(self.hass)
        try:
            resp = await cloud_device_list(session, user_id, token)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("device list failed: %s", err)
            return await self.async_step_token()
        dev_token: str | None = None
        for entry in resp.get("DeviceList", []) or []:
            if int(entry.get("DeviceId", -1)) == self._pending.device_id:
                dev_token = str(entry.get("DeviceToken") or entry.get("Token") or "")
                break
        if not dev_token:
            return await self.async_step_token()
        data = {
            CONF_HOST: self._pending.ip,
            CONF_PORT: DEFAULT_PORT,
            CONF_DEVICE_ID: self._pending.device_id,
            CONF_DEVICE_TOKEN: dev_token,
            CONF_DEVICE_NAME: self._pending.device_name,
            CONF_MAC: self._pending.mac,
            CONF_HARDWARE: self._pending.hardware,
        }
        await self.async_set_unique_id(str(self._pending.device_id))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._pending.device_name or self._pending.ip, data=data
        )


async def _verify(hass, data: dict[str, Any]) -> bool:
    session = async_get_clientsession(hass)
    client = DivoomLocalClient(
        session=session,
        host=data[CONF_HOST],
        device_id=data.get(CONF_DEVICE_ID),
        device_token=data.get(CONF_DEVICE_TOKEN),
        port=data.get(CONF_PORT, DEFAULT_PORT),
    )
    try:
        await client.get_all_conf()
    except (DivoomAuthError, DivoomConnectionError):
        return False
    return True
