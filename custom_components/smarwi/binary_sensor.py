# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2024 Jakub Jirutka <jakub@jirutka.cz>
from typing_extensions import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SIGNAL_DISCOVERY_NEW
from .device import SmarwiConfigEntry, SmarwiDeviceProp
from .entity import SmarwiEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmarwiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SMARWI binary sensor entities based on a config entry."""
    devices = entry.runtime_data

    async def async_discover_device(entry_id: str, device_id: str) -> None:
        if entry_id != entry.entry_id:
            return  # not for us
        assert devices[device_id] is not None
        async_add_entities([SmarwiRidgeInsideBinarySensor(devices[device_id])])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_DISCOVERY_NEW, async_discover_device)
    )


class SmarwiRidgeInsideBinarySensor(SmarwiEntity, BinarySensorEntity):
    """Representation of the SMARWI "ridge inside" sensor."""

    entity_description = BinarySensorEntityDescription(
        key="ridge_inside",
        device_class=BinarySensorDeviceClass.TAMPER,
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    @override
    async def async_handle_update(self, changed_props: set[SmarwiDeviceProp]) -> None:
        if SmarwiDeviceProp.RIDGE_INSIDE in changed_props:
            self._attr_is_on = not self.device.ridge_inside
            self.async_write_ha_state()
