from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
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
    if coordinator.is_mqtt:
        async_add_entities([DivoomOnlineSensor(coordinator, entry)])


class DivoomOnlineSensor(CoordinatorEntity[DivoomCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DivoomCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        data = entry.data
        dev_id = data[CONF_DEVICE_ID]
        self._attr_unique_id = f"{DOMAIN}_{dev_id}_online"
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
        return self.coordinator.online

    @property
    def available(self) -> bool:
        return True
