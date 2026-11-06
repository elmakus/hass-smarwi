"""Public HA setup and tilt-service tests with an entirely mocked MQTT client."""

import socket
from unittest.mock import Mock, call

import probatio
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_mqtt_message
from pytest_homeassistant.typing import MqttMockHAClient, MqttMockPahoClient

from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_CURRENT_TILT_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceNotSupported
from homeassistant.helpers import entity_registry as er

from custom_components.smarwi.const import CONF_REMOTE_ID, DOMAIN

REMOTE_ID = "offline_remote"
DEVICE_ID = "offline_serial"
BASE_TOPIC = f"ion/{REMOTE_ID}/%{DEVICE_ID}"
STATUS = "cid:Offline fixture\nfix:1\npos:o\nro:0\ns:250"


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Also block loopback connections allowed by the upstream test fixtures."""

    def fail(*args: object, **kwargs: object) -> None:
        """Fail rather than contact any real network or MQTT broker."""
        raise AssertionError("Service tests must not use network sockets or DNS")

    for name in ("connect", "connect_ex", "sendto", "bind", "listen"):
        monkeypatch.setattr(socket.socket, name, fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(socket, "getaddrinfo", fail)


@pytest.fixture
def mqtt_client_mock(mqtt_client_mock: MqttMockPahoClient) -> MqttMockPahoClient:
    """Complete the upstream mock's missing Paho socket-close callback."""

    def disconnect() -> int:
        """Let HA cancel its real MQTT timer through the normal callback."""
        mqtt_client_mock.on_socket_close(
            mqtt_client_mock, None, Mock(fileno=Mock(return_value=-1))
        )
        return 0

    mqtt_client_mock.disconnect.side_effect = disconnect
    return mqtt_client_mock


@pytest.fixture
async def smarwi_entry(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient
) -> MockConfigEntry:
    """Set up the real integration and feed only synthetic discovery/status."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_REMOTE_ID: REMOTE_ID})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/online", "1")
    await hass.async_block_till_done()
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", STATUS)
    await hass.async_block_till_done()
    # A separate update avoids claiming that cached initial state is hydrated.
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/online", "1")
    await hass.async_block_till_done()
    mqtt_mock.async_publish.reset_mock()
    return entry


@pytest.fixture
def cover_id(smarwi_entry: MockConfigEntry, entity_registry: er.EntityRegistry) -> str:
    """Find the actual cover registered by the integration, not a fake entity."""
    entity_id = entity_registry.async_get_entity_id(
        "cover", DOMAIN, f"{DEVICE_ID}_cover"
    )
    assert entity_id is not None
    registry_entry = entity_registry.async_get(entity_id)
    assert registry_entry is not None
    assert registry_entry.config_entry_id == smarwi_entry.entry_id
    return entity_id


async def test_state_machine_has_only_window_tilt_features(
    hass: HomeAssistant, cover_id: str
) -> None:
    """Expose the exact tilt-only contract through HA's real state machine."""
    state = hass.states.get(cover_id)
    assert state is not None
    expected = (
        CoverEntityFeature.OPEN_TILT
        | CoverEntityFeature.CLOSE_TILT
        | CoverEntityFeature.SET_TILT_POSITION
        | CoverEntityFeature.STOP_TILT
    )
    assert state.attributes["device_class"] == CoverDeviceClass.WINDOW
    assert state.attributes["supported_features"] == expected
    assert ATTR_CURRENT_POSITION not in state.attributes
    assert ATTR_CURRENT_TILT_POSITION not in state.attributes


@pytest.mark.parametrize(
    ("service", "data", "payload"),
    [
        ("open_cover_tilt", {}, "open;100"),
        ("close_cover_tilt", {}, "close"),
        ("set_cover_tilt_position", {ATTR_TILT_POSITION: 0}, "close"),
        ("set_cover_tilt_position", {ATTR_TILT_POSITION: 10}, "open;10"),
        ("set_cover_tilt_position", {ATTR_TILT_POSITION: 30}, "open;30"),
        ("set_cover_tilt_position", {ATTR_TILT_POSITION: 100}, "open;100"),
    ],
)
async def test_native_tilt_services_publish(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    cover_id: str,
    service: str,
    data: dict[str, int],
    payload: str,
) -> None:
    """Route native HA tilt services to the real device code and mock transport."""
    await hass.services.async_call(
        "cover", service, {"entity_id": cover_id, **data}, blocking=True
    )
    mqtt_mock.async_publish.assert_called_once_with(
        f"{BASE_TOPIC}/cmd", payload, 2, False, message_expiry_interval=None
    )


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="P6: device.async_open(1) currently encodes close",
)
async def test_one_percent_is_an_open_target(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient, cover_id: str
) -> None:
    """Record the known 1% wire defect without changing production behavior."""
    await hass.services.async_call(
        "cover",
        "set_cover_tilt_position",
        {"entity_id": cover_id, ATTR_TILT_POSITION: 1},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(
        f"{BASE_TOPIC}/cmd", "open;1", 2, False, message_expiry_interval=None
    )


@pytest.mark.parametrize(
    "data", [{ATTR_TILT_POSITION: -1}, {ATTR_TILT_POSITION: 101}, {}, {"position": 30}]
)
async def test_invalid_tilt_payloads_never_publish(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    cover_id: str,
    data: dict[str, int],
) -> None:
    """Reject invalid or standard-position payloads at HA's public schema."""
    with pytest.raises(probatio.Invalid):
        await hass.services.async_call(
            "cover",
            "set_cover_tilt_position",
            {"entity_id": cover_id, **data},
            blocking=True,
        )
    mqtt_mock.async_publish.assert_not_called()


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("open_cover", {}),
        ("close_cover", {}),
        ("set_cover_position", {"position": 30}),
        ("stop_cover", {}),
    ],
)
async def test_standard_services_are_not_tilt_aliases(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    cover_id: str,
    service: str,
    data: dict[str, int],
) -> None:
    """HA rejects explicitly targeted standard actions for this tilt-only cover."""
    with pytest.raises(ServiceNotSupported):
        await hass.services.async_call(
            "cover", service, {"entity_id": cover_id, **data}, blocking=True
        )
    mqtt_mock.async_publish.assert_not_called()


async def test_closed_update_reports_zero_tilt_only(
    hass: HomeAssistant, cover_id: str
) -> None:
    """Pass synthetic closed telemetry through MQTT callbacks to HA's state."""
    async_fire_mqtt_message(
        hass, f"{BASE_TOPIC}/status", STATUS.replace("pos:o", "pos:c")
    )
    await hass.async_block_till_done()
    state = hass.states.get(cover_id)
    assert state is not None
    assert state.state == "closed"
    assert state.attributes[ATTR_CURRENT_TILT_POSITION] == 0
    assert ATTR_CURRENT_POSITION not in state.attributes


async def test_stop_tilt_then_idle_status_invalidates_inferred_position(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient, cover_id: str
) -> None:
    """Characterize the inherited double Stop, without endorsing physical holding."""
    await hass.services.async_call(
        "cover",
        "set_cover_tilt_position",
        {"entity_id": cover_id, ATTR_TILT_POSITION: 30},
        blocking=True,
    )
    async_fire_mqtt_message(
        hass, f"{BASE_TOPIC}/status", STATUS.replace("s:250", "s:210")
    )
    await hass.async_block_till_done()
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", STATUS)
    await hass.async_block_till_done()
    state = hass.states.get(cover_id)
    assert state is not None
    assert state.attributes[ATTR_CURRENT_TILT_POSITION] == 30

    async_fire_mqtt_message(
        hass, f"{BASE_TOPIC}/status", STATUS.replace("s:250", "s:210")
    )
    await hass.async_block_till_done()
    state = hass.states.get(cover_id)
    assert state is not None
    assert state.state == "opening"
    mqtt_mock.async_publish.reset_mock()
    await hass.services.async_call(
        "cover", "stop_cover_tilt", {"entity_id": cover_id}, blocking=True
    )
    assert mqtt_mock.async_publish.call_args_list == [
        call(f"{BASE_TOPIC}/cmd", "stop", 2, False, message_expiry_interval=None),
        call(f"{BASE_TOPIC}/cmd", "stop", 2, False, message_expiry_interval=None),
    ]
    # The inherited entity writes HA state on telemetry, not immediately on Stop.
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", STATUS)
    await hass.async_block_till_done()
    state = hass.states.get(cover_id)
    assert state is not None
    assert ATTR_CURRENT_TILT_POSITION not in state.attributes
    assert ATTR_CURRENT_POSITION not in state.attributes


async def test_unload_removes_the_cover(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    smarwi_entry: MockConfigEntry,
    cover_id: str,
) -> None:
    """Unload the entry and ensure subsequent discovery cannot recreate entities."""
    assert await hass.config_entries.async_unload(smarwi_entry.entry_id)
    await hass.async_block_till_done()
    assert smarwi_entry.state is ConfigEntryState.NOT_LOADED
    state = hass.states.get(cover_id)
    assert state is None or state.state == "unavailable"
    mqtt_mock.async_subscribe.reset_mock()
    mqtt_mock.async_publish.reset_mock()
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/online", "1")
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", STATUS)
    await hass.async_block_till_done()
    assert hass.states.get(cover_id) == state
    mqtt_mock.async_subscribe.assert_not_called()
    mqtt_mock.async_publish.assert_not_called()
