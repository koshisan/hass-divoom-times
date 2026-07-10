from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CMD_CONNECT_APP,
    CMD_DISCONNECT_MQTT,
    CMD_HEARTBEAT,
    DOMAIN,
    MQTT_TOPIC_APP,
    MQTT_TOPIC_DEVICE,
    MQTT_TOPIC_LWT,
)

_LOGGER = logging.getLogger(__name__)


def signal_device_message(device_id: int) -> str:
    """Dispatcher signal for a specific device's MQTT messages."""
    return f"{DOMAIN}_mqtt_msg_{device_id}"


class MqttTransport:
    """Publishes commands to `DivoomApp` and dispatches inbound messages.

    Subscription is per-config-entry; multiple entries share the topic but
    dispatch by DeviceId to avoid cross-talk.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: int,
        user_id: int,
        cloud_token: int,
    ) -> None:
        self._hass = hass
        self._device_id = device_id
        self._user_id = user_id
        self._cloud_token = cloud_token
        self._unsubs: list[Callable[[], None]] = []

    @property
    def device_id(self) -> int:
        return self._device_id

    def update_cloud_credentials(self, user_id: int, cloud_token: int) -> None:
        """Refresh after a reauth."""
        self._user_id = user_id
        self._cloud_token = cloud_token

    async def async_setup(self) -> None:
        unsub_device = await mqtt.async_subscribe(
            self._hass, MQTT_TOPIC_DEVICE, self._on_message, qos=1
        )
        unsub_lwt = await mqtt.async_subscribe(
            self._hass, MQTT_TOPIC_LWT, self._on_message, qos=1
        )
        self._unsubs = [unsub_device, unsub_lwt]

    async def async_teardown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    async def send(
        self, command: str, extra: dict[str, Any] | None = None
    ) -> None:
        payload: dict[str, Any] = {
            "Command": command,
            "DeviceId": self._device_id,
            "UserId": self._user_id,
            "Token": self._cloud_token,
        }
        if extra:
            payload.update(extra)
        await mqtt.async_publish(
            self._hass, MQTT_TOPIC_APP, json.dumps(payload), qos=1
        )

    @callback
    def _on_message(self, msg: mqtt.ReceiveMessage) -> None:
        raw = msg.payload
        try:
            data = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
        except (ValueError, UnicodeDecodeError):
            return
        did = data.get("DeviceId")
        if did != self._device_id:
            return
        # Dispatcher fan-out — coordinator listens, updates its state, then
        # notifies entities. Cheap even under a heartbeat storm.
        async_dispatcher_send(
            self._hass, signal_device_message(self._device_id), msg.topic, data
        )
