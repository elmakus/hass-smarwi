# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2024 Jakub Jirutka <jakub@jirutka.cz>
"""Integration for Vektiva SMARWI window opener."""

from asyncio import CancelledError

from homeassistant.components import mqtt
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_REMOTE_ID, LOGGER
from .device import SmarwiConfigEntry, SmarwiDevice

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.COVER,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: SmarwiConfigEntry) -> bool:
    """Set up SMARWI from a config entry."""

    # Make sure MQTT integration is enabled and the client is available.
    if not await mqtt.async_wait_for_mqtt_client(hass):
        raise ConfigEntryNotReady("MQTT integration is not available")

    remote_id: str = entry.data[CONF_REMOTE_ID]
    entry.runtime_data = {}
    devices = entry.runtime_data

    @callback
    def connection_status_changed(connected: bool) -> None:
        if not connected:
            for device in devices.values():
                device.async_broker_disconnected()

    entry.async_on_unload(
        mqtt.async_subscribe_connection_status(hass, connection_status_changed)
    )

    async def device_discovery(msg: mqtt.ReceiveMessage) -> None:
        # Topic looks like ion/<remote_id>/%<device_id>/online.
        device_segment = msg.topic.split("/")[2]
        if not device_segment.startswith("%") or len(device_segment) == 1:
            LOGGER.warning("Ignoring malformed SMARWI discovery topic")
            return
        device_id = device_segment[1:]

        # Check if this device is already known
        if device_id in devices:
            return

        LOGGER.info(f"Discovered new SMARWI device: {device_id}")

        devices[device_id] = device = SmarwiDevice(hass, entry, device_id)
        try:
            await device.async_init()
        except (Exception, CancelledError):
            if devices.get(device_id) is device:
                del devices[device_id]
            raise

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Discover SMARWI devices with the configured REMOTE ID.
    LOGGER.debug(f"Subscribing to ion/{remote_id}/+/online")
    entry.async_on_unload(
        await mqtt.async_subscribe(hass, f"ion/{remote_id}/+/online", device_discovery)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SmarwiConfigEntry) -> bool:
    """Handle removal of an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
