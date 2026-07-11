from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .api import DivoomError
from .const import (
    CMD_SEND_HTTP_TEXT,
    CONF_DEVICE_ID,
    CONF_DEVICE_TYPE,
    DOMAIN,
    SERVICE_SEND_TEXT,
    SUPPORTS_SEND_TEXT,
)
from .coordinator import DivoomCoordinator

_LOGGER = logging.getLogger(__name__)

SEND_TEXT_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("text"): cv.string,
        vol.Optional("text_id", default=1): vol.All(int, vol.Range(min=1, max=19)),
        vol.Optional("color", default="#FFFFFF"): cv.string,
        vol.Optional("speed", default=100): vol.All(int, vol.Range(min=1, max=200)),
        vol.Optional("lcd_id", default=0): vol.All(int, vol.Range(min=0, max=4)),
        vol.Optional("x", default=0): vol.All(int, vol.Range(min=0, max=64)),
        vol.Optional("y", default=24): vol.All(int, vol.Range(min=0, max=64)),
        vol.Optional("font", default=4): vol.All(int, vol.Range(min=0, max=8)),
        vol.Optional("width", default=56): vol.All(int, vol.Range(min=8, max=64)),
        vol.Optional("align", default=1): vol.All(int, vol.Range(min=0, max=2)),
        vol.Optional("dir", default=0): vol.All(int, vol.Range(min=0, max=1)),
    }
)


def _resolve_coordinator(
    hass: HomeAssistant, target_device_id: str
) -> DivoomCoordinator | None:
    """Match either a Divoom DeviceId or a HA device registry id."""
    for coordinator in hass.data.get(DOMAIN, {}).values():
        entry = coordinator.entry
        if (
            str(entry.data.get(CONF_DEVICE_ID)) == target_device_id
            or entry.entry_id == target_device_id
        ):
            return coordinator
    return None


async def _async_send_text(hass: HomeAssistant, call: ServiceCall) -> None:
    coordinator = _resolve_coordinator(hass, call.data["device_id"])
    if coordinator is None:
        _LOGGER.warning("send_text: unknown device_id %s", call.data["device_id"])
        return
    if coordinator.entry.data.get(CONF_DEVICE_TYPE) not in SUPPORTS_SEND_TEXT:
        _LOGGER.warning(
            "send_text: device type %s does not support Draw/SendHttpText",
            coordinator.entry.data.get(CONF_DEVICE_TYPE),
        )
        return
    payload: dict[str, Any] = {
        "TextId": call.data["text_id"],
        "x": call.data["x"],
        "y": call.data["y"],
        "dir": call.data["dir"],
        "font": call.data["font"],
        "TextWidth": call.data["width"],
        "speed": call.data["speed"],
        "TextString": call.data["text"],
        "color": call.data["color"],
        "align": call.data["align"],
        "LcdId": call.data["lcd_id"],
    }
    try:
        await coordinator.async_send(CMD_SEND_HTTP_TEXT, payload)
    except DivoomError as err:
        _LOGGER.warning("send_text failed: %s", err)


def async_register(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SEND_TEXT):
        return
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_TEXT,
        lambda call: hass.async_create_task(_async_send_text(hass, call)),
        schema=SEND_TEXT_SCHEMA,
    )


def async_unregister(hass: HomeAssistant) -> None:
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_SEND_TEXT)
