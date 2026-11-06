# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2024 Jakub Jirutka <jakub@jirutka.cz>
from typing import Any  # pyright:ignore[reportAny]
from typing_extensions import override

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
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
    """Set up SMARWI switch entities based on a config entry."""
    devices = entry.runtime_data

    async def async_discover_device(entry_id: str, device_id: str) -> None:
        if entry_id != entry.entry_id:
            return  # not for us
        assert devices[device_id] is not None
        async_add_entities([SmarwiRidgeFixedSwitch(devices[device_id])])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_DISCOVERY_NEW, async_discover_device)
    )


class SmarwiRidgeFixedSwitch(SmarwiEntity, SwitchEntity):
    """Representation of the SMARWI fixation sensor/switch."""

    entity_description = SwitchEntityDescription(
        key="ridge_fix",
        device_class=SwitchDeviceClass.SWITCH,
    )

    @override
    async def async_turn_on(self, **_: Any) -> None:
        await self.device.async_toggle_ridge_fixed(True)

    @override
    async def async_turn_off(self, **_: Any) -> None:
        await self.device.async_toggle_ridge_fixed(False)

    @override
    async def async_handle_update(self, changed_props: set[SmarwiDeviceProp]) -> None:
        if SmarwiDeviceProp.RIDGE_FIXED in changed_props:
            self._attr_is_on = self.device.ridge_fixed
            self.async_write_ha_state()
