from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    DivoomAuthError,
    DivoomCloudClient,
    DivoomConnectionError,
    DivoomError,
    LocalTransport,
    OwnedDevice,
)
from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_EMAIL,
    CONF_HOST,
    CONF_LOCAL_TOKEN,
    CONF_MAC,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_TRANSPORT,
    CONF_USER_ID,
    DOMAIN,
    HARDWARE_NAMES,
    LOCAL_PROFILES,
    TRANSPORT_CLOUD,
    TRANSPORT_LOCAL,
)

_LOGGER = logging.getLogger(__name__)


class DivoomTimesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._client: DivoomCloudClient | None = None
        self._devices: list[OwnedDevice] = []
        self._picked: OwnedDevice | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = DivoomCloudClient(session)
            try:
                await client.login(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            except DivoomAuthError:
                errors["base"] = "invalid_auth"
            except DivoomConnectionError:
                errors["base"] = "cannot_connect"
            except DivoomError as err:  # noqa: BLE001
                _LOGGER.warning("login failed: %s", err)
                errors["base"] = "unknown"
            else:
                self._client = client
                try:
                    self._devices = await client.list_devices()
                except DivoomError as err:
                    _LOGGER.warning("device list failed: %s", err)
                    errors["base"] = "no_devices_found"
                else:
                    if not self._devices:
                        errors["base"] = "no_devices_found"
                    else:
                        return await self.async_step_pick_device()

        schema = vol.Schema(
            {vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str}
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            chosen = next(
                (
                    d
                    for d in self._devices
                    if str(d.device_id) == user_input["device_id"]
                ),
                None,
            )
            if chosen is None:
                errors["device_id"] = "unknown_device"
            else:
                self._picked = chosen
                profile = LOCAL_PROFILES.get(chosen.device_type)
                if profile is None:
                    # Unknown hardware — cloud is the only safe default.
                    return await self._create_cloud_entry(chosen)
                if not profile.needs_local_token:
                    # Times Frame path — verify local reachability and go local.
                    ok = await self._verify_local(chosen, None)
                    if ok:
                        return await self._create_local_entry(chosen, None)
                    return await self._create_cloud_entry(chosen)
                # Times Gate — ask for LocalToken next.
                return await self.async_step_local_token()

        options = {
            str(d.device_id): (
                f"{d.device_name} — {HARDWARE_NAMES.get(d.device_type, f'HW{d.device_type}')}"
                f" ({'online' if d.online else 'offline'})"
            )
            for d in self._devices
        }
        schema = vol.Schema({vol.Required("device_id"): vol.In(options)})
        return self.async_show_form(
            step_id="pick_device", data_schema=schema, errors=errors
        )

    async def async_step_local_token(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        assert self._picked is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            raw = user_input.get(CONF_LOCAL_TOKEN)
            if raw in (None, "", "0"):
                # User skipped — fall back to cloud transport.
                return await self._create_cloud_entry(self._picked)
            try:
                token = int(raw)
            except (TypeError, ValueError):
                errors["base"] = "invalid_token"
            else:
                if await self._verify_local(self._picked, token):
                    return await self._create_local_entry(self._picked, token)
                errors["base"] = "local_token_rejected"

        schema = vol.Schema({vol.Optional(CONF_LOCAL_TOKEN): str})
        return self.async_show_form(
            step_id="local_token",
            data_schema=schema,
            description_placeholders={
                "name": self._picked.device_name,
                "ip": self._picked.private_ip,
            },
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = DivoomCloudClient(session)
            try:
                await client.login(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            except DivoomAuthError:
                errors["base"] = "invalid_auth"
            except DivoomConnectionError:
                errors["base"] = "cannot_connect"
            else:
                entry = self._get_reauth_entry()
                new_data = {
                    **entry.data,
                    CONF_USER_ID: client.user_id,
                    CONF_TOKEN: client.token,
                }
                self.hass.config_entries.async_update_entry(entry, data=new_data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
        schema = vol.Schema(
            {vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str}
        )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors
        )

    async def _verify_local(
        self, device: OwnedDevice, local_token: int | None
    ) -> bool:
        profile = LOCAL_PROFILES.get(device.device_type)
        if profile is None or not device.private_ip:
            return False
        session = async_get_clientsession(self.hass)
        transport = LocalTransport(
            session=session,
            host=device.private_ip,
            port=profile.port,
            path=profile.path,
            method=profile.method,
            local_token=local_token,
        )
        try:
            await transport.send("Channel/GetAllConf")
        except DivoomAuthError:
            return False
        except DivoomError as err:
            _LOGGER.debug("local verify failed: %s", err)
            return False
        return True

    async def _create_local_entry(
        self, device: OwnedDevice, local_token: int | None
    ) -> FlowResult:
        await self.async_set_unique_id(str(device.device_id))
        self._abort_if_unique_id_configured()
        data: dict[str, Any] = {
            CONF_TRANSPORT: TRANSPORT_LOCAL,
            CONF_DEVICE_ID: device.device_id,
            CONF_DEVICE_NAME: device.device_name,
            CONF_DEVICE_TYPE: device.device_type,
            CONF_HOST: device.private_ip,
            CONF_MAC: device.mac,
        }
        if local_token is not None:
            data[CONF_LOCAL_TOKEN] = local_token
        return self.async_create_entry(
            title=device.device_name or f"Divoom {device.device_id}", data=data
        )

    async def _create_cloud_entry(self, device: OwnedDevice) -> FlowResult:
        assert self._client is not None
        await self.async_set_unique_id(str(device.device_id))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=device.device_name or f"Divoom {device.device_id}",
            data={
                CONF_TRANSPORT: TRANSPORT_CLOUD,
                CONF_USER_ID: self._client.user_id,
                CONF_TOKEN: self._client.token,
                CONF_DEVICE_ID: device.device_id,
                CONF_DEVICE_NAME: device.device_name,
                CONF_DEVICE_TYPE: device.device_type,
                CONF_HOST: device.private_ip,
                CONF_MAC: device.mac,
            },
        )
