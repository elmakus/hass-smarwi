"""Redacted SMARWI diagnostics from cached MQTT observations."""

from homeassistant.core import HomeAssistant

from .device import SmarwiConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SmarwiConfigEntry
) -> dict[str, list[dict[str, bool | int | str | None]]]:
    """Return allowlisted telemetry, never raw messages or device identifiers."""
    return {
        "devices": [
            {
                "available": device.available,
                "status_source": device.status_source,
                "state_code": device.state_code.name,
                "closed": device.closed,
                "ridge_fixed": device.ridge_fixed,
                "ridge_inside": device.ridge_inside,
                "rssi": device.rssi,
            }
            for device in entry.runtime_data.values()
        ]
    }
