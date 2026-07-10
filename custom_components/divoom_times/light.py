from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_HARDWARE,
    CONF_HOST,
    CONF_MAC,
    DOMAIN,
    HARDWARE_NAMES,
)
from .coordinator import DivoomCoordinator


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
        dev_id = data.get(CONF_DEVICE_ID) or data.get(CONF_HOST)
        self._attr_unique_id = f"{DOMAIN}_{dev_id}_light"
        mac = data.get(CONF_MAC)
        hw = data.get(CONF_HARDWARE)
        connections = {("mac", mac)} if mac else set()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(dev_id))},
            connections=connections,
            manufacturer="Divoom",
            model=HARDWARE_NAMES.get(hw or 0, f"HW{hw}"),
            name=data.get(CONF_DEVICE_NAME) or data.get(CONF_HOST),
            configuration_url=f"http://{data[CONF_HOST]}",
        )

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data or {}
        light_switch = data.get("LightSwitch")
        if light_switch is not None:
            return bool(light_switch)
        b = data.get("Brightness")
        return None if b is None else b > 0

    @property
    def brightness(self) -> int | None:
        b = (self.coordinator.data or {}).get("Brightness")
        if b is None:
            return None
        return round(int(b) * 255 / 100)

    async def async_turn_on(self, **kwargs: Any) -> None:
        client = self.coordinator.client
        brightness_255 = kwargs.get(ATTR_BRIGHTNESS)
        if brightness_255 is not None:
            pct = max(1, round(int(brightness_255) * 100 / 255))
            await client.set_screen_on(True)
            await client.set_brightness(pct)
        else:
            await client.set_screen_on(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_screen_on(False)
        await self.coordinator.async_request_refresh()
