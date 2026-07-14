from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DivoomError
from .const import (
    CHANNEL_LABEL_TO_INDEX,
    CHANNEL_LABELS,
    CMD_SET_AMBIENT_LIGHT,
    CMD_SET_INDEX,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_MAC,
    DOMAIN,
    FRAME_EFFECT_LABEL_TO_INDEX,
    FRAME_EFFECT_LABELS,
    HARDWARE_NAMES,
    SUPPORTS_AMBIENT_LIGHT,
    SUPPORTS_CHANNEL_SELECT,
)
from .coordinator import DivoomCoordinator

_LOGGER = logging.getLogger(__name__)

FRAME_STATE_EFFECT = "_frame_effect"
FRAME_STATE_EQ = "_frame_eq_on"
FRAME_STATE_BRIGHTNESS = "_rgb_brightness"
FRAME_STATE_COLOR = "_rgb_color"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DivoomCoordinator = hass.data[DOMAIN][entry.entry_id]
    device_type = entry.data.get(CONF_DEVICE_TYPE)
    entities: list[SelectEntity] = []
    if device_type in SUPPORTS_CHANNEL_SELECT:
        entities.append(DivoomChannelSelect(coordinator, entry))
    if device_type in SUPPORTS_AMBIENT_LIGHT:
        entities.append(DivoomFrameEffectSelect(coordinator, entry))
    if entities:
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


class DivoomChannelSelect(CoordinatorEntity[DivoomCoordinator], SelectEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "channel"
    _attr_name = "Channel"
    _attr_options = list(CHANNEL_LABELS.values())

    def __init__(self, coordinator: DivoomCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry.data[CONF_DEVICE_ID]}_channel"
        self._attr_device_info = _device_info(entry)

    @property
    def current_option(self) -> str | None:
        idx = (self.coordinator.data or {}).get("_SelectIndex")
        if isinstance(idx, int):
            return CHANNEL_LABELS.get(idx)
        return None

    async def async_select_option(self, option: str) -> None:
        idx = CHANNEL_LABEL_TO_INDEX.get(option)
        if idx is None:
            return
        try:
            await self.coordinator.async_send(CMD_SET_INDEX, {"SelectIndex": idx})
        except DivoomError as err:
            _LOGGER.warning("SetIndex failed: %s", err)
            raise
        current = dict(self.coordinator.data or {})
        current["_SelectIndex"] = idx
        self.coordinator.async_set_updated_data(current)


class DivoomFrameEffectSelect(CoordinatorEntity[DivoomCoordinator], SelectEntity):
    """Times Frame Lichteffekt (SelectEffect 0..7).

    Labels are icon-based guesses; only index 7 (Static) is user-confirmed.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "effect"
    _attr_name = "Effect"
    _attr_options = list(FRAME_EFFECT_LABELS.values())

    def __init__(self, coordinator: DivoomCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry.data[CONF_DEVICE_ID]}_effect"
        self._attr_device_info = _device_info(entry)

    @property
    def current_option(self) -> str | None:
        idx = (self.coordinator.data or {}).get(FRAME_STATE_EFFECT)
        if isinstance(idx, int):
            return FRAME_EFFECT_LABELS.get(idx)
        return None

    async def async_select_option(self, option: str) -> None:
        idx = FRAME_EFFECT_LABEL_TO_INDEX.get(option)
        if idx is None:
            return
        current = self.coordinator.data or {}
        pct = int(current.get(FRAME_STATE_BRIGHTNESS, 80))
        rgb = current.get(FRAME_STATE_COLOR) or (255, 255, 255)
        eq = int(current.get(FRAME_STATE_EQ, 0))
        payload = {
            "Brightness": pct,
            "Color": _hex(tuple(int(c) for c in rgb)),
            "ColorCycle": 0,
            "EqOnOff": eq,
            "SelectEffect": idx,
        }
        try:
            await self.coordinator.async_send(CMD_SET_AMBIENT_LIGHT, payload)
        except DivoomError as err:
            _LOGGER.warning("SetAmbientLight effect change failed: %s", err)
            raise
        new = dict(current)
        new[FRAME_STATE_EFFECT] = idx
        self.coordinator.async_set_updated_data(new)
