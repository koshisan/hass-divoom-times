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
    CMD_SET_INDEX,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_MAC,
    DOMAIN,
    HARDWARE_NAMES,
    SUPPORTS_CHANNEL_SELECT,
)
from .coordinator import DivoomCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.data.get(CONF_DEVICE_TYPE) not in SUPPORTS_CHANNEL_SELECT:
        return
    coordinator: DivoomCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DivoomChannelSelect(coordinator, entry)])


class DivoomChannelSelect(CoordinatorEntity[DivoomCoordinator], SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "Channel"
    _attr_options = list(CHANNEL_LABELS.values())

    def __init__(self, coordinator: DivoomCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        data = entry.data
        dev_id = data[CONF_DEVICE_ID]
        self._attr_unique_id = f"{DOMAIN}_{dev_id}_channel"
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
    def current_option(self) -> str | None:
        data = self.coordinator.data or {}
        # Channel/GetAllConf doesn't include the channel; Channel/GetIndex
        # returns SelectIndex as a per-LCD array. When we sent SetIndex,
        # coordinator stashes the last value.
        idx = data.get("_SelectIndex")
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
        # Persist local view — no read-back exposes the current channel cleanly.
        current = dict(self.coordinator.data or {})
        current["_SelectIndex"] = idx
        self.coordinator.async_set_updated_data(current)
