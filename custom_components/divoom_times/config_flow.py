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
    OwnedDevice,
)
from .const import (
    CONF_CLOUD_TOKEN,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_EMAIL,
    CONF_HOST,
    CONF_LOCAL_TOKEN,
    CONF_MAC,
    CONF_PASSWORD,
    CONF_USER_ID,
    DOMAIN,
    HARDWARE_NAMES,
)

_LOGGER = logging.getLogger(__name__)


class DivoomTimesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 4

    def __init__(self) -> None:
        self._client: DivoomCloudClient | None = None
        self._devices: list[OwnedDevice] = []

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
            except DivoomError as err:
                _LOGGER.warning("login failed: %s", err)
                errors["base"] = "unknown"
            else:
                self._client = client
                try:
                    self._devices = await client.list_devices()
                except DivoomAuthError:
                    errors["base"] = "invalid_auth"
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
        assert self._client is not None
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
                await self.async_set_unique_id(str(chosen.device_id))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=chosen.device_name or f"Divoom {chosen.device_id}",
                    data={
                        CONF_USER_ID: self._client.user_id,
                        CONF_CLOUD_TOKEN: self._client.token,
                        CONF_DEVICE_ID: chosen.device_id,
                        CONF_DEVICE_NAME: chosen.device_name,
                        CONF_DEVICE_TYPE: chosen.device_type,
                        CONF_HOST: chosen.private_ip,
                        CONF_MAC: chosen.mac,
                        CONF_LOCAL_TOKEN: chosen.local_token,
                    },
                )

        options = {
            str(d.device_id): (
                f"{d.device_name} — {HARDWARE_NAMES.get(d.device_type, f'HW{d.device_type}')}"
            )
            for d in self._devices
        }
        schema = vol.Schema({vol.Required("device_id"): vol.In(options)})
        return self.async_show_form(
            step_id="pick_device", data_schema=schema, errors=errors
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
                target_id = entry.data.get(CONF_DEVICE_ID)
                try:
                    devices = await client.list_devices()
                except DivoomError as err:
                    _LOGGER.warning("reauth device list failed: %s", err)
                    errors["base"] = "no_devices_found"
                else:
                    match = next(
                        (d for d in devices if d.device_id == target_id), None
                    )
                    if match is None:
                        errors["base"] = "unknown_device"
                    else:
                        new_data = {
                            **entry.data,
                            CONF_USER_ID: client.user_id,
                            CONF_CLOUD_TOKEN: client.token,
                            CONF_LOCAL_TOKEN: match.local_token,
                            CONF_HOST: match.private_ip or entry.data[CONF_HOST],
                        }
                        self.hass.config_entries.async_update_entry(
                            entry, data=new_data
                        )
                        await self.hass.config_entries.async_reload(entry.entry_id)
                        return self.async_abort(reason="reauth_successful")

        schema = vol.Schema(
            {vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str}
        )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors
        )
