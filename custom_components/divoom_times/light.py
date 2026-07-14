from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DivoomError
from .const import (
    CMD_ON_OFF_SCREEN,
    CMD_SET_BRIGHTNESS,
    CMD_SET_RGB_INFO,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_MAC,
    DOMAIN,
    HARDWARE_NAMES,
    SUPPORTS_RGB,
)
from .coordinator import DivoomCoordinator

_LOGGER = logging.getLogger(__name__)

# Internal state keys for the RGB layer. Prefixed with _rgb so they can
# coexist with the pixel-display state coming back from GetAllConf.
_RGB_ON = "_rgb_on"
_RGB_BRIGHTNESS = "_rgb_brightness"
_RGB_COLOR = "_rgb_color"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DivoomCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[LightEntity] = [DivoomScreenLight(coordinator, entry)]
    if entry.data.get(CONF_DEVICE_TYPE) in SUPPORTS_RGB:
        entities.append(DivoomRgbLight(coordinator, entry))
    async_add_entities(entities)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    data = entry.data
    hw = data.get(CONF_DEVICE_TYPE, 0)
    mac = data.get(CONF_MAC)
    connections = {("mac", mac)} if mac else set()
    return DeviceInfo(
        identifiers={(DOMAIN, str(data[CONF_DEVICE_ID]))},
        connections=connections,
        manufacturer="Divoom",
        model=HARDWARE_NAMES.get(hw, f"HW{hw}"),
        name=data.get(CONF_DEVICE_NAME) or f"Divoom {data[CONF_DEVICE_ID]}",
    )


class DivoomScreenLight(CoordinatorEntity[DivoomCoordinator], LightEntity):
    """The pixel display: on/off + brightness. No colour — content is the face."""

    _attr_has_entity_name = True
    _attr_translation_key = "screen"
    _attr_name = "Screen"
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, coordinator: DivoomCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry.data[CONF_DEVICE_ID]}_screen"
        self._attr_device_info = _device_info(entry)

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
            _LOGGER.warning("screen turn_on failed: %s", err)
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.async_send(CMD_ON_OFF_SCREEN, {"OnOff": 0})
        except DivoomError as err:
            _LOGGER.warning("screen turn_off failed: %s", err)
            raise


class DivoomRgbLight(CoordinatorEntity[DivoomCoordinator], LightEntity):
    """The ambient RGB layer around the pixel display."""

    _attr_has_entity_name = True
    _attr_translation_key = "rgb"
    _attr_name = "RGB"
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB

    def __init__(self, coordinator: DivoomCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry.data[CONF_DEVICE_ID]}_rgb"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool | None:
        # Optimistic — GetRGBInfo returns nothing. Assume on until told otherwise.
        return bool((self.coordinator.data or {}).get(_RGB_ON, True))

    @property
    def brightness(self) -> int | None:
        pct = (self.coordinator.data or {}).get(_RGB_BRIGHTNESS)
        if not isinstance(pct, int):
            return 255
        return max(0, min(255, round(pct * 255 / 100)))

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        rgb = (self.coordinator.data or {}).get(_RGB_COLOR)
        if isinstance(rgb, (list, tuple)) and len(rgb) == 3:
            return tuple(int(c) for c in rgb)  # type: ignore[return-value]
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        current = dict(self.coordinator.data or {})
        pct = current.get(_RGB_BRIGHTNESS, 80)
        rgb = current.get(_RGB_COLOR, (255, 255, 255))
        if ATTR_BRIGHTNESS in kwargs:
            pct = max(1, round(int(kwargs[ATTR_BRIGHTNESS]) * 100 / 255))
        if ATTR_RGB_COLOR in kwargs:
            rgb = tuple(int(c) for c in kwargs[ATTR_RGB_COLOR])
        color_hex = "#{:02X}{:02X}{:02X}".format(*rgb)
        payload = {
            "Brightness": int(pct),
            "Color": color_hex,
            "ColorCycle": 0,
            "OnOff": 1,
            "KeyOnOff": 1,
            "LightList": [],
            "SelectLightIndex": 0,
        }
        try:
            await self.coordinator.async_send(CMD_SET_RGB_INFO, payload)
        except DivoomError as err:
            _LOGGER.warning("rgb turn_on failed: %s", err)
            raise
        current[_RGB_ON] = True
        current[_RGB_BRIGHTNESS] = int(pct)
        current[_RGB_COLOR] = tuple(rgb)
        self.coordinator.async_set_updated_data(current)

    async def async_turn_off(self, **kwargs: Any) -> None:
        current = dict(self.coordinator.data or {})
        payload = {
            "Brightness": int(current.get(_RGB_BRIGHTNESS, 80)),
            "Color": "#000000",
            "ColorCycle": 0,
            "OnOff": 0,
            "KeyOnOff": 0,
            "LightList": [],
            "SelectLightIndex": 0,
        }
        try:
            await self.coordinator.async_send(CMD_SET_RGB_INFO, payload)
        except DivoomError as err:
            _LOGGER.warning("rgb turn_off failed: %s", err)
            raise
        current[_RGB_ON] = False
        self.coordinator.async_set_updated_data(current)
