from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DivoomError
from .const import (
    CMD_SET_AMBIENT_LIGHT,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_MAC,
    DOMAIN,
    HARDWARE_NAMES,
    SUPPORTS_AMBIENT_LIGHT,
)
from .coordinator import DivoomCoordinator
from .select import (
    FRAME_STATE_BRIGHTNESS,
    FRAME_STATE_COLOR,
    FRAME_STATE_EFFECT,
    FRAME_STATE_EQ,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.data.get(CONF_DEVICE_TYPE) not in SUPPORTS_AMBIENT_LIGHT:
        return
    coordinator: DivoomCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DivoomFrameEqSwitch(coordinator, entry)])


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


class DivoomFrameEqSwitch(CoordinatorEntity[DivoomCoordinator], SwitchEntity):
    """Times Frame EQ / audio-reactive toggle (EqOnOff)."""

    _attr_has_entity_name = True
    _attr_translation_key = "eq"
    _attr_name = "EQ rhythm"
    _attr_icon = "mdi:waveform"

    def __init__(self, coordinator: DivoomCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry.data[CONF_DEVICE_ID]}_eq"
        data = entry.data
        hw = data.get(CONF_DEVICE_TYPE, 0)
        mac = data.get(CONF_MAC)
        connections = {("mac", mac)} if mac else set()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(data[CONF_DEVICE_ID]))},
            connections=connections,
            manufacturer="Divoom",
            model=HARDWARE_NAMES.get(hw, f"HW{hw}"),
            name=data.get(CONF_DEVICE_NAME) or f"Divoom {data[CONF_DEVICE_ID]}",
        )

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get(FRAME_STATE_EQ, 0))

    async def _async_apply(self, eq: int) -> None:
        current = self.coordinator.data or {}
        pct = int(current.get(FRAME_STATE_BRIGHTNESS, 80))
        rgb = current.get(FRAME_STATE_COLOR) or (255, 255, 255)
        effect = int(current.get(FRAME_STATE_EFFECT, 7))
        payload = {
            "Brightness": pct,
            "Color": _hex(tuple(int(c) for c in rgb)),
            "ColorCycle": 0,
            "EqOnOff": eq,
            "SelectEffect": effect,
        }
        try:
            await self.coordinator.async_send(CMD_SET_AMBIENT_LIGHT, payload)
        except DivoomError as err:
            _LOGGER.warning("EQ toggle failed: %s", err)
            raise
        new = dict(current)
        new[FRAME_STATE_EQ] = eq
        self.coordinator.async_set_updated_data(new)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_apply(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_apply(0)
