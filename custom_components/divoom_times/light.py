from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DivoomError
from .const import (
    CMD_ON_OFF_SCREEN,
    CMD_SET_BRIGHTNESS,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_MAC,
    CONF_TRANSPORT,
    DOMAIN,
    HARDWARE_NAMES,
    TRANSPORT_MQTT,
)
from .coordinator import DivoomCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DivoomCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DivoomLight(coordinator, entry)])


class DivoomLight(CoordinatorEntity[DivoomCoordinator], LightEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, coordinator: DivoomCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        data = entry.data
        dev_id = data[CONF_DEVICE_ID]
        self._attr_unique_id = f"{DOMAIN}_{dev_id}_light"
        # MQTT feeds arrive from device heartbeats + response echoes; HTTP
        # polls GetAllConf. Both give real read-back — no assumed state.
        self._attr_assumed_state = data[CONF_TRANSPORT] == TRANSPORT_MQTT and False
        hw = data.get(CONF_DEVICE_TYPE, 0)
        mac = data.get(CONF_MAC)
        connections = {("mac", mac)} if mac else set()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(dev_id))},
            connections=connections,
            manufacturer="Divoom",
            model=HARDWARE_NAMES.get(hw, f"HW{hw}"),
            name=data.get(CONF_DEVICE_NAME) or f"Divoom {dev_id}",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.online or not self.coordinator.is_mqtt

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data or {}
        v = data.get("LightSwitch")
        if isinstance(v, int):
            return bool(v)
        b = data.get("Brightness")
        return None if b is None else b > 0

    @property
    def brightness(self) -> int | None:
        b = (self.coordinator.data or {}).get("Brightness")
        if not isinstance(b, int):
            return None
        return max(0, min(255, round(b * 255 / 100)))

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            if ATTR_BRIGHTNESS in kwargs:
                pct = max(1, round(int(kwargs[ATTR_BRIGHTNESS]) * 100 / 255))
                await self.coordinator.async_send(CMD_ON_OFF_SCREEN, {"OnOff": 1})
                await self.coordinator.async_send(CMD_SET_BRIGHTNESS, {"Brightness": pct})
            else:
                await self.coordinator.async_send(CMD_ON_OFF_SCREEN, {"OnOff": 1})
        except DivoomError as err:
            _LOGGER.warning("turn_on failed: %s", err)
            raise
        if not self.coordinator.is_mqtt:
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.async_send(CMD_ON_OFF_SCREEN, {"OnOff": 0})
        except DivoomError as err:
            _LOGGER.warning("turn_off failed: %s", err)
            raise
        if not self.coordinator.is_mqtt:
            await self.coordinator.async_request_refresh()
