from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DivoomError
from .const import (
    CMD_ON_OFF_SCREEN,
    CMD_SET_AMBIENT_LIGHT,
    CMD_SET_BRIGHTNESS,
    CMD_SET_RGB_INFO,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_MAC,
    DOMAIN,
    GATE_LIGHTLIST_STATIC,
    GATE_LIGHT_ZONES,
    HARDWARE_NAMES,
    SUPPORTS_AMBIENT_LIGHT,
    SUPPORTS_RGB_INFO,
)
from .coordinator import DivoomCoordinator

_LOGGER = logging.getLogger(__name__)

# Per-zone RGB state key namespace.
_FRAME_EFFECT = "_frame_effect"
_FRAME_EQ = "_frame_eq_on"


def _zone_key(zone_slug: str, field: str) -> str:
    """State-dict key for one Gate zone (e.g. `_rgb_backlight_color`)."""
    return f"_rgb_{zone_slug}_{field}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DivoomCoordinator = hass.data[DOMAIN][entry.entry_id]
    device_type = entry.data.get(CONF_DEVICE_TYPE)
    entities: list[LightEntity] = [DivoomScreenLight(coordinator, entry)]
    if device_type in SUPPORTS_RGB_INFO:
        for zone_index, (slug, name) in GATE_LIGHT_ZONES.items():
            entities.append(
                DivoomGateZoneLight(coordinator, entry, zone_index, slug, name)
            )
    elif device_type in SUPPORTS_AMBIENT_LIGHT:
        entities.append(DivoomFrameRgbLight(coordinator, entry))
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


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


class DivoomScreenLight(CoordinatorEntity[DivoomCoordinator], LightEntity):
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


class _RgbBase(CoordinatorEntity[DivoomCoordinator], LightEntity):
    _attr_has_entity_name = True
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB


class DivoomGateZoneLight(_RgbBase):
    """One Times Gate ambient zone (All / Surround / Backlight).

    Payload shape reverse-engineered from usausa/divoom-tool: LightList is an
    array of `{"SelectEffect": N}` objects, not hex strings. Three entries
    with SelectEffect=5 (Static) plus ColorCycle=0 holds a solid colour.
    """

    _attr_translation_key = "rgb_zone"

    def __init__(
        self,
        coordinator: DivoomCoordinator,
        entry: ConfigEntry,
        zone_index: int,
        slug: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._zone_index = zone_index
        self._slug = slug
        self._attr_name = f"RGB {name}"
        self._attr_unique_id = f"{DOMAIN}_{entry.data[CONF_DEVICE_ID]}_rgb_{slug}"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return bool(
            (self.coordinator.data or {}).get(_zone_key(self._slug, "on"), True)
        )

    @property
    def brightness(self) -> int | None:
        pct = (self.coordinator.data or {}).get(
            _zone_key(self._slug, "brightness"), 80
        )
        return max(0, min(255, round(int(pct) * 255 / 100)))

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        rgb = (self.coordinator.data or {}).get(_zone_key(self._slug, "color"))
        if isinstance(rgb, (list, tuple)) and len(rgb) == 3:
            return tuple(int(c) for c in rgb)  # type: ignore[return-value]
        return (255, 255, 255)

    def _resolve(self, kwargs: dict[str, Any]) -> tuple[int, tuple[int, int, int]]:
        current = self.coordinator.data or {}
        pct = int(current.get(_zone_key(self._slug, "brightness"), 80))
        rgb: tuple[int, int, int] = tuple(  # type: ignore[assignment]
            current.get(_zone_key(self._slug, "color")) or (255, 255, 255)
        )
        if ATTR_BRIGHTNESS in kwargs:
            pct = max(1, round(int(kwargs[ATTR_BRIGHTNESS]) * 100 / 255))
        if ATTR_RGB_COLOR in kwargs:
            rgb = tuple(int(c) for c in kwargs[ATTR_RGB_COLOR])  # type: ignore[assignment]
        return pct, rgb

    async def _send(
        self,
        on: int,
        pct: int,
        color_hex: str,
        key_on_off: int,
    ) -> None:
        payload = {
            "Brightness": pct,
            "Color": color_hex,
            "OnOff": on,
            "KeyOnOff": key_on_off,
            "ColorCycle": 0,
            "SelectLightIndex": self._zone_index,
            "LightList": GATE_LIGHTLIST_STATIC,
        }
        await self.coordinator.async_send(CMD_SET_RGB_INFO, payload)

    def _persist(
        self, on: bool, pct: int, rgb: tuple[int, int, int] | None
    ) -> None:
        current = dict(self.coordinator.data or {})
        current[_zone_key(self._slug, "on")] = on
        current[_zone_key(self._slug, "brightness")] = pct
        if rgb is not None:
            current[_zone_key(self._slug, "color")] = tuple(rgb)
        self.coordinator.async_set_updated_data(current)

    async def async_turn_on(self, **kwargs: Any) -> None:
        pct, rgb = self._resolve(kwargs)
        try:
            await self._send(on=1, pct=pct, color_hex=_hex(rgb), key_on_off=1)
        except DivoomError as err:
            _LOGGER.warning("gate zone %s turn_on failed: %s", self._slug, err)
            raise
        self._persist(True, pct, rgb)

    async def async_turn_off(self, **kwargs: Any) -> None:
        pct = int(
            (self.coordinator.data or {}).get(
                _zone_key(self._slug, "brightness"), 80
            )
        )
        try:
            await self._send(on=0, pct=pct, color_hex="#000000", key_on_off=0)
        except DivoomError as err:
            _LOGGER.warning("gate zone %s turn_off failed: %s", self._slug, err)
            raise
        self._persist(False, pct, None)


class DivoomFrameRgbLight(_RgbBase):
    """Times Frame sidelight via Channel/SetAmbientLight."""

    _attr_translation_key = "rgb"
    _attr_name = "RGB"

    def __init__(self, coordinator: DivoomCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry.data[CONF_DEVICE_ID]}_rgb"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get("_rgb_on", True))

    @property
    def brightness(self) -> int | None:
        pct = (self.coordinator.data or {}).get("_rgb_brightness", 80)
        return max(0, min(255, round(int(pct) * 255 / 100)))

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        rgb = (self.coordinator.data or {}).get("_rgb_color")
        if isinstance(rgb, (list, tuple)) and len(rgb) == 3:
            return tuple(int(c) for c in rgb)  # type: ignore[return-value]
        return (255, 255, 255)

    def _resolve(self, kwargs: dict[str, Any]) -> tuple[int, tuple[int, int, int]]:
        current = self.coordinator.data or {}
        pct = int(current.get("_rgb_brightness", 80))
        rgb: tuple[int, int, int] = tuple(  # type: ignore[assignment]
            current.get("_rgb_color") or (255, 255, 255)
        )
        if ATTR_BRIGHTNESS in kwargs:
            pct = max(1, round(int(kwargs[ATTR_BRIGHTNESS]) * 100 / 255))
        if ATTR_RGB_COLOR in kwargs:
            rgb = tuple(int(c) for c in kwargs[ATTR_RGB_COLOR])  # type: ignore[assignment]
        return pct, rgb

    async def async_turn_on(self, **kwargs: Any) -> None:
        pct, rgb = self._resolve(kwargs)
        current = self.coordinator.data or {}
        effect = int(current.get(_FRAME_EFFECT, 7))
        eq = int(current.get(_FRAME_EQ, 0))
        payload = {
            "Brightness": pct,
            "Color": _hex(rgb),
            "ColorCycle": 0,
            "EqOnOff": eq,
            "SelectEffect": effect,
        }
        try:
            await self.coordinator.async_send(CMD_SET_AMBIENT_LIGHT, payload)
        except DivoomError as err:
            _LOGGER.warning("frame rgb turn_on failed: %s", err)
            raise
        new = dict(current)
        new["_rgb_on"] = True
        new["_rgb_brightness"] = pct
        new["_rgb_color"] = tuple(rgb)
        self.coordinator.async_set_updated_data(new)

    async def async_turn_off(self, **kwargs: Any) -> None:
        current = self.coordinator.data or {}
        effect = int(current.get(_FRAME_EFFECT, 7))
        eq = int(current.get(_FRAME_EQ, 0))
        payload = {
            "Brightness": 0,
            "Color": "#000000",
            "ColorCycle": 0,
            "EqOnOff": eq,
            "SelectEffect": effect,
        }
        try:
            await self.coordinator.async_send(CMD_SET_AMBIENT_LIGHT, payload)
        except DivoomError as err:
            _LOGGER.warning("frame rgb turn_off failed: %s", err)
            raise
        new = dict(current)
        new["_rgb_on"] = False
        self.coordinator.async_set_updated_data(new)
