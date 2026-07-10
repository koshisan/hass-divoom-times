from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_connect
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
    CMD_HEARTBEAT,
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
    MQTT_TOPIC_DEVICE,
    MQTT_TOPIC_LWT,
    TRANSPORT_MQTT,
)
from .mqtt_transport import MqttTransport, signal_device_message

_LOGGER = logging.getLogger(__name__)


class DivoomCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Push-driven for MQTT, poll-driven for HTTP.

    Both variants expose the same interface to entities via `data`.
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
        self._unsub_dispatcher = None

        if self._is_mqtt:
            self.mqtt = MqttTransport(
                hass=hass,
                device_id=self.device_id,
                user_id=entry.data[CONF_USER_ID],
                cloud_token=entry.data[CONF_CLOUD_TOKEN],
            )
            self.http = None
        else:
            self.mqtt = None
            session = async_get_clientsession(hass)
            profile = HTTP_PROFILES[entry.data[CONF_DEVICE_TYPE]]
            self.http = HttpTransport(
                session=session,
                host=entry.data[CONF_HOST],
                port=profile.port,
                path=profile.path,
                method=profile.method,
                local_token=entry.data[CONF_LOCAL_TOKEN],
            )

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
            self._unsub_dispatcher = async_dispatcher_connect(
                self.hass,
                signal_device_message(self.device_id),
                self._on_mqtt_message,
            )
            # We're driven by heartbeats — nothing to prime.
            self.async_set_updated_data({})
        else:
            await self.async_config_entry_first_refresh()

    async def async_teardown(self) -> None:
        if self._unsub_dispatcher:
            self._unsub_dispatcher()
            self._unsub_dispatcher = None
        if self.mqtt is not None:
            await self.mqtt.async_teardown()

    async def async_send(
        self, command: str, extra: dict[str, Any] | None = None
    ) -> None:
        """Fire-and-forget for MQTT; awaited HTTP round trip otherwise."""
        if self._is_mqtt:
            await self.mqtt.send(command, extra)
        else:
            try:
                await self.http.send(command, extra)
            except DivoomAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err

    async def _async_update_data(self) -> dict[str, Any]:
        if self._is_mqtt:
            # Push-driven — DataUpdateCoordinator shouldn't be scheduled here
            # because update_interval is None. This branch is defensive.
            return self.data or {}
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

    @callback
    def _on_mqtt_message(self, topic: str, data: dict[str, Any]) -> None:
        command = data.get("Command")
        current = dict(self.data or {})
        current["_last_command"] = command
        if topic == MQTT_TOPIC_LWT and command == CMD_DISCONNECT_MQTT:
            self._online = False
        elif command in (CMD_HEARTBEAT, CMD_CONNECT_APP):
            self._online = True
            self._last_heartbeat = time.time()
            wifi = data.get("WifiSingal")
            if isinstance(wifi, int):
                current["WifiSingal"] = wifi
        elif command == "Channel/OnOffScreen":
            if isinstance(data.get("OnOff"), int):
                current["LightSwitch"] = int(data["OnOff"])
        elif command == "Channel/SetBrightness":
            if isinstance(data.get("Brightness"), int):
                current["Brightness"] = int(data["Brightness"])
        current["Online"] = 1 if self._online else 0
        self.async_set_updated_data(current)
