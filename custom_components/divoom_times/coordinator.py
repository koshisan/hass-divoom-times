from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    DivoomAuthError,
    DivoomCommandError,
    DivoomConnectionError,
    HttpTransport,
)
from .const import (
    CMD_CONNECT_APP,
    CMD_DISCONNECT_MQTT,
    CMD_GET_ALL_CONF,
    CMD_GET_ON_OFF_SCREEN,
    CMD_HEARTBEAT,
    CMD_ON_OFF_SCREEN,
    CMD_SET_BRIGHTNESS,
    CONF_CLOUD_TOKEN,
    CONF_DEVICE_ID,
    CONF_DEVICE_TYPE,
    CONF_HOST,
    CONF_LOCAL_TOKEN,
    CONF_TRANSPORT,
    CONF_USER_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HTTP_PROFILES,
    MQTT_HTTP_POLL_INTERVAL,
    MQTT_ONOFF_POLL_INTERVAL,
    MQTT_TOPIC_LWT,
    TRANSPORT_MQTT,
)
from .mqtt_transport import MqttTransport, signal_device_message

_LOGGER = logging.getLogger(__name__)


class DivoomCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """MQTT push + HTTP fallback for state read-back.

    For an MQTT-transport entry we still run periodic HTTP `Channel/GetAllConf`
    polls because Times Gate only replies to a handful of Get commands over
    MQTT — brightness in particular is unreadable that way. Commands still
    go out over MQTT.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        interval = (
            None
            if entry.data[CONF_TRANSPORT] == TRANSPORT_MQTT
            else timedelta(seconds=DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.data.get(CONF_DEVICE_ID)}",
            update_interval=interval,
        )
        self.entry = entry
        self.device_id: int = entry.data[CONF_DEVICE_ID]
        self._is_mqtt: bool = entry.data[CONF_TRANSPORT] == TRANSPORT_MQTT
        self._online: bool = False
        self._last_heartbeat: float | None = None
        self._unsubs: list = []

        # HTTP is always available if we know the LocalToken — used by MQTT
        # entries too, as a supplementary poller for brightness.
        session = async_get_clientsession(hass)
        profile = HTTP_PROFILES.get(entry.data[CONF_DEVICE_TYPE])
        if profile is not None and entry.data.get(CONF_HOST):
            self.http = HttpTransport(
                session=session,
                host=entry.data[CONF_HOST],
                port=profile.port,
                path=profile.path,
                method=profile.method,
                local_token=entry.data[CONF_LOCAL_TOKEN],
            )
        else:
            self.http = None

        if self._is_mqtt:
            self.mqtt = MqttTransport(
                hass=hass,
                device_id=self.device_id,
                user_id=entry.data[CONF_USER_ID],
                cloud_token=entry.data[CONF_CLOUD_TOKEN],
            )
        else:
            self.mqtt = None

    @property
    def is_mqtt(self) -> bool:
        return self._is_mqtt

    @property
    def online(self) -> bool:
        return self._online

    @property
    def last_heartbeat(self) -> float | None:
        return self._last_heartbeat

    async def async_setup(self) -> None:
        if self._is_mqtt:
            await self.mqtt.async_setup()
            self._unsubs.append(
                async_dispatcher_connect(
                    self.hass,
                    signal_device_message(self.device_id),
                    self._on_mqtt_message,
                )
            )
            self.async_set_updated_data({})
            # Prime state and set up hybrid pollers.
            self.hass.async_create_task(self._prime_state())
            self._unsubs.append(
                async_track_time_interval(
                    self.hass,
                    self._poll_onoff_via_mqtt,
                    timedelta(seconds=MQTT_ONOFF_POLL_INTERVAL),
                )
            )
            if self.http is not None:
                self._unsubs.append(
                    async_track_time_interval(
                        self.hass,
                        self._poll_state_via_http,
                        timedelta(seconds=MQTT_HTTP_POLL_INTERVAL),
                    )
                )
        else:
            await self.async_config_entry_first_refresh()

    async def async_teardown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self.mqtt is not None:
            await self.mqtt.async_teardown()

    async def async_send(
        self, command: str, extra: dict[str, Any] | None = None
    ) -> None:
        """Fire a command; MQTT for MQTT entries, HTTP otherwise."""
        try:
            if self._is_mqtt:
                await self.mqtt.send(command, extra)
                # MQTT commands are silent; nudge the read-back paths so the UI
                # doesn't sit for the full poll interval on a stale value.
                self.hass.async_create_task(self._refresh_after_command())
            else:
                await self.http.send(command, extra)
                await self.async_request_refresh()
        except DivoomAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err

    async def _async_update_data(self) -> dict[str, Any]:
        if self._is_mqtt:
            return self.data or {}
        assert self.http is not None
        try:
            resp = await self.http.send(CMD_GET_ALL_CONF)
        except DivoomAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DivoomConnectionError as err:
            self._online = False
            raise UpdateFailed(f"connection: {err}") from err
        except DivoomCommandError as err:
            _LOGGER.debug("GetAllConf refused: %s", err)
            return self.data or {}
        self._online = True
        return resp

    async def _prime_state(self) -> None:
        await asyncio.sleep(0.2)
        await self._poll_onoff_via_mqtt()
        if self.http is not None:
            await self._poll_state_via_http()

    async def _poll_onoff_via_mqtt(self, _now=None) -> None:
        try:
            await self.mqtt.send(CMD_GET_ON_OFF_SCREEN)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("MQTT GetOnOffScreen failed: %s", err)

    async def _poll_state_via_http(self, _now=None) -> None:
        if self.http is None:
            return
        try:
            resp = await self.http.send(CMD_GET_ALL_CONF)
        except DivoomAuthError as err:
            _LOGGER.warning("HTTP GetAllConf auth failure: %s", err)
            return
        except (DivoomConnectionError, DivoomCommandError) as err:
            _LOGGER.debug("HTTP GetAllConf failed: %s", err)
            return
        current = dict(self.data or {})
        for key in (
            "Brightness",
            "LightSwitch",
            "MirrorFlag",
            "TemperatureMode",
            "Time24Flag",
            "DateFormat",
        ):
            if key in resp:
                current[key] = resp[key]
        current["Online"] = 1 if self._online or self._is_mqtt else 0
        self.async_set_updated_data(current)

    async def _refresh_after_command(self) -> None:
        # Give the device a beat to apply, then re-read.
        await asyncio.sleep(0.4)
        await self._poll_onoff_via_mqtt()
        if self.http is not None:
            await self._poll_state_via_http()

    @callback
    def _on_mqtt_message(self, topic: str, data: dict[str, Any]) -> None:
        command = data.get("Command")
        current = dict(self.data or {})
        if topic == MQTT_TOPIC_LWT and command == CMD_DISCONNECT_MQTT:
            self._online = False
        elif command in (CMD_HEARTBEAT, CMD_CONNECT_APP):
            self._online = True
            self._last_heartbeat = time.time()
            wifi = data.get("WifiSingal")
            if isinstance(wifi, int):
                current["WifiSingal"] = wifi
        elif command == CMD_GET_ON_OFF_SCREEN:
            on = data.get("OnOff")
            if isinstance(on, int):
                current["LightSwitch"] = int(on)
                self._online = True
        elif command == CMD_ON_OFF_SCREEN:
            on = data.get("OnOff")
            if isinstance(on, int):
                current["LightSwitch"] = int(on)
        elif command == CMD_SET_BRIGHTNESS:
            b = data.get("Brightness")
            if isinstance(b, int):
                current["Brightness"] = int(b)
        current["Online"] = 1 if self._online else 0
        self.async_set_updated_data(current)
