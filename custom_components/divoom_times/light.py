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
    DOMAIN,
    HARDWARE_NAMES,
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
    _attr_assumed_state = True

    def __init__(self, coordinator: DivoomCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        data = entry.data
        dev_id = data[CONF_DEVICE_ID]
        self._attr_unique_id = f"{DOMAIN}_{dev_id}_light"
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
    def is_on(self) -> bool:
        return self.coordinator.is_on

    @property
    def brightness(self) -> int | None:
        pct = self.coordinator.last_brightness
        if pct is None:
            return None
        return max(0, min(255, round(pct * 255 / 100)))

    async def async_turn_on(self, **kwargs: Any) -> None:
        client = self.coordinator.client
        device_id = self.coordinator.device_id
        try:
            if ATTR_BRIGHTNESS in kwargs:
                pct = max(1, round(int(kwargs[ATTR_BRIGHTNESS]) * 100 / 255))
                await client.send_command(
                    CMD_ON_OFF_SCREEN, device_id, {"OnOff": 1}
                )
                await client.send_command(
                    CMD_SET_BRIGHTNESS, device_id, {"Brightness": pct}
                )
                self.coordinator.record_brightness(pct)
                self.coordinator.record_on_off(True)
            else:
                await client.send_command(
                    CMD_ON_OFF_SCREEN, device_id, {"OnOff": 1}
                )
                self.coordinator.record_on_off(True)
        except DivoomError as err:
            _LOGGER.warning("turn_on failed for %s: %s", device_id, err)
            raise
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        client = self.coordinator.client
        device_id = self.coordinator.device_id
        try:
            await client.send_command(CMD_ON_OFF_SCREEN, device_id, {"OnOff": 0})
        except DivoomError as err:
            _LOGGER.warning("turn_off failed for %s: %s", device_id, err)
            raise
        self.coordinator.record_on_off(False)
        self.async_write_ha_state()
