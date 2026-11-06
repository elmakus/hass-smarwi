"""Public HA setup and tilt-service tests with an entirely mocked MQTT client."""

import asyncio
import logging
import socket
from unittest.mock import AsyncMock, Mock, call

import probatio
import pytest
from pytest_homeassistant.common import (
    MockConfigEntry,
    MockMqttReasonCode,
    async_fire_mqtt_message,
)
from pytest_homeassistant.typing import MqttMockHAClient, MqttMockPahoClient

from homeassistant.components import mqtt
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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import async_get_platforms

from custom_components.smarwi.const import CONF_REMOTE_ID, DOMAIN
from custom_components.smarwi.cover import SmarwiCover
from custom_components.smarwi.device import SmarwiDevice, SmarwiDeviceProp, StateCode
from custom_components.smarwi.entity import SmarwiEntity

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
def broker_connection(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    mqtt_client_mock: MqttMockPahoClient,
    monkeypatch: pytest.MonkeyPatch,
) -> Mock:
    """Drive official Paho callbacks and expose the real HA connection flag."""
    real_client = mqtt_mock._mock_wraps
    # Upstream assigns a shadow connected=True on its wrapping MagicMock.
    monkeypatch.setattr(
        type(mqtt_mock),
        "connected",
        property(lambda _: real_client.connected),
        raising=False,
    )

    def transition(connected: bool) -> None:
        handler = (
            mqtt_client_mock.on_connect if connected else mqtt_client_mock.on_disconnect
        )
        handler(mqtt_client_mock, None, 0, MockMqttReasonCode())
        assert real_client.connected is connected
        assert mqtt.is_connected(hass) is connected

    return Mock(side_effect=transition)


@pytest.fixture
def dispatcher_spy(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Observe production dispatch calls without suppressing their callbacks."""
    spy = Mock(wraps=async_dispatcher_send)
    monkeypatch.setattr("custom_components.smarwi.device.async_dispatcher_send", spy)
    return spy


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


def test_config_flow_schema_uses_home_assistant_validation() -> None:
    """Keep the native schema and selector boundary covered without entry setup."""
    from custom_components.smarwi.config_flow import DATA_SCHEMA

    assert isinstance(DATA_SCHEMA, probatio.Schema)
    assert DATA_SCHEMA({CONF_REMOTE_ID: REMOTE_ID}) == {CONF_REMOTE_ID: REMOTE_ID}
    for invalid in (
        {},
        {CONF_REMOTE_ID: None},
        {CONF_REMOTE_ID: 1},
        {CONF_REMOTE_ID: []},
    ):
        with pytest.raises(probatio.Invalid):
            DATA_SCHEMA(invalid)


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
    ("online", "fixed", "inside", "cover_state", "ridge_state", "fix_state"),
    [
        ("1", "1", "0", "closed", "off", "on"),
        ("1", "0", "1", "unavailable", "on", "off"),
        ("0", "1", "0", "unavailable", "unavailable", "unavailable"),
    ],
)
async def test_entities_hydrate_cached_telemetry_before_attachment(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    entity_registry: er.EntityRegistry,
    monkeypatch: pytest.MonkeyPatch,
    online: str,
    fixed: str,
    inside: str,
    cover_state: str,
    ridge_state: str,
    fix_state: str,
) -> None:
    """Read pre-attachment caches, then keep listening across unload/reload."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_REMOTE_ID: REMOTE_ID})
    entry.add_to_hass(hass)
    status_ready = asyncio.Event()
    original_added = SmarwiEntity.async_added_to_hass

    async def add_after_status(entity: SmarwiEntity) -> None:
        # Force the initial status dispatch to finish before attaching listeners.
        await status_ready.wait()
        await original_added(entity)

    def dispatch(hass: HomeAssistant, signal: str, *args: object) -> None:
        async_dispatcher_send(hass, signal, *args)
        if args and isinstance(args[0], set) and SmarwiDeviceProp.STATE_CODE in args[0]:
            status_ready.set()

    monkeypatch.setattr(SmarwiEntity, "async_added_to_hass", add_after_status)
    monkeypatch.setattr(
        "custom_components.smarwi.device.async_dispatcher_send", dispatch
    )

    def entity_id(platform: str, key: str) -> str:
        result = entity_registry.async_get_entity_id(
            platform, DOMAIN, f"{DEVICE_ID}_{key}"
        )
        assert result is not None
        return result

    for _ in range(2):
        status_ready.clear()
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        # The first online discovers MQTT subscriptions; the second caches online.
        # Both precede status/entity discovery, unlike the historical fixture.
        async_fire_mqtt_message(hass, f"{BASE_TOPIC}/online", online)
        await hass.async_block_till_done()
        async_fire_mqtt_message(hass, f"{BASE_TOPIC}/online", online)
        await hass.async_block_till_done()
        async_fire_mqtt_message(hass, f"{BASE_TOPIC}/config/advanced", "vpct:80")
        await hass.async_block_till_done()
        mqtt_mock.async_publish.reset_mock()
        async_fire_mqtt_message(
            hass,
            f"{BASE_TOPIC}/status",
            f"cid:Offline fixture\nfix:{fixed}\npos:c\nro:{inside}\ns:250",
        )
        await hass.async_block_till_done()

        cover = hass.states.get(entity_id("cover", "cover"))
        assert cover is not None
        assert cover.state == cover_state
        if cover_state == "closed":
            assert cover.attributes[ATTR_CURRENT_TILT_POSITION] == 0
            assert cover.attributes["state_code"] == "IDLE"
        for platform, key, expected in (
            ("binary_sensor", "ridge_inside", ridge_state),
            ("switch", "ridge_fix", fix_state),
            ("number", "max_open_position", "80" if online == "1" else "unavailable"),
            ("number", "move_speed", "unavailable"),
        ):
            state = hass.states.get(entity_id(platform, key))
            assert state is not None
            assert state.state == expected
        mqtt_mock.async_publish.assert_not_called()

        # Future telemetry still updates the same attached entities; no commands.
        async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", STATUS)
        async_fire_mqtt_message(
            hass, f"{BASE_TOPIC}/config/advanced", "vpct:75\nospd:40"
        )
        await hass.async_block_till_done()
        cover = hass.states.get(entity_id("cover", "cover"))
        assert cover is not None
        assert cover.state == ("open" if online == "1" else "unavailable")
        assert ATTR_CURRENT_TILT_POSITION not in cover.attributes
        number = hass.states.get(entity_id("number", "max_open_position"))
        assert number is not None
        assert number.state == ("75" if online == "1" else "unavailable")
        for platform, key, expected in (
            ("binary_sensor", "ridge_inside", "off"),
            ("switch", "ridge_fix", "on"),
            ("number", "move_speed", "40"),
        ):
            state = hass.states.get(entity_id(platform, key))
            assert state is not None
            assert state.state == (expected if online == "1" else "unavailable")
        mqtt_mock.async_publish.assert_not_called()

        device: SmarwiDevice = hass.data[DOMAIN][entry.entry_id][DEVICE_ID]
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        with monkeypatch.context() as patch:
            writes = Mock()
            patch.setattr(Entity, "async_write_ha_state", writes)
            async_dispatcher_send(hass, device.signal_update, set(SmarwiDeviceProp))
            await hass.async_block_till_done()
            writes.assert_not_called()
        assert entry.state is ConfigEntryState.NOT_LOADED


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


@pytest.mark.parametrize(
    ("service", "data", "target", "payload"),
    [
        ("open_cover_tilt", {}, 100, "open;100"),
        ("close_cover_tilt", {}, 0, "close"),
        ("set_cover_tilt_position", {ATTR_TILT_POSITION: 0}, 0, "close"),
        ("set_cover_tilt_position", {ATTR_TILT_POSITION: 1}, 1, "open;1"),
        ("set_cover_tilt_position", {ATTR_TILT_POSITION: 30}, 30, "open;30"),
        ("set_cover_tilt_position", {ATTR_TILT_POSITION: 100}, 100, "open;100"),
    ],
)
async def test_explicit_tilt_services_publish_at_equal_inferred_position(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    cover_id: str,
    service: str,
    data: dict[str, int],
    target: int,
    payload: str,
) -> None:
    """Never suppress explicit commands based only on a cached/inferred target."""
    await hass.services.async_call(
        "cover", service, {"entity_id": cover_id, **data}, blocking=True
    )
    mqtt_mock.async_publish.assert_called_once_with(
        f"{BASE_TOPIC}/cmd", payload, 2, False, message_expiry_interval=None
    )
    async_fire_mqtt_message(
        hass, f"{BASE_TOPIC}/status", STATUS.replace("s:250", "s:210")
    )
    await hass.async_block_till_done()
    idle_status = STATUS.replace("pos:o", "pos:c") if target == 0 else STATUS
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", idle_status)
    await hass.async_block_till_done()
    before = hass.states.get(cover_id)
    assert before is not None
    cover = next(
        platform.entities[cover_id]
        for platform in async_get_platforms(hass, DOMAIN)
        if cover_id in platform.entities
    )
    assert isinstance(cover, SmarwiCover)
    assert cover._position == target
    assert before.attributes.get(ATTR_CURRENT_TILT_POSITION) == (
        0 if target == 0 else None
    )
    mqtt_mock.async_publish.reset_mock()

    for _ in range(2):
        await hass.services.async_call(
            "cover", service, {"entity_id": cover_id, **data}, blocking=True
        )
    assert (
        mqtt_mock.async_publish.call_args_list
        == [call(f"{BASE_TOPIC}/cmd", payload, 2, False, message_expiry_interval=None)]
        * 2
    )
    after = hass.states.get(cover_id)
    assert after is not None
    assert after.state == before.state
    assert after.attributes == before.attributes


@pytest.mark.parametrize(
    ("service", "data", "payload"),
    [
        ("open_cover_tilt", {}, "open;100"),
        ("close_cover_tilt", {}, "close"),
        ("set_cover_tilt_position", {ATTR_TILT_POSITION: 30}, "open;30"),
    ],
)
async def test_late_publish_completion_does_not_rearm_target_after_stop(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    cover_id: str,
    service: str,
    data: dict[str, int],
    payload: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A delayed QoS acknowledgement must not undo a subsequent native Stop."""
    cover = next(
        platform.entities[cover_id]
        for platform in async_get_platforms(hass, DOMAIN)
        if cover_id in platform.entities
    )
    assert isinstance(cover, SmarwiCover)
    async_fire_mqtt_message(
        hass, f"{BASE_TOPIC}/status", STATUS.replace("s:250", "s:210")
    )
    await hass.async_block_till_done()
    assert cover.device.state_code.is_moving()
    assert cover.is_opening
    publish_started = asyncio.Event()
    publish_completed = asyncio.Event()

    async def gated_publish(*args: object, **kwargs: object) -> None:
        """Delay only the first action's completion; both Stop publishes proceed."""
        if not publish_started.is_set():
            publish_started.set()
            await publish_completed.wait()

    publish = AsyncMock(side_effect=gated_publish)
    monkeypatch.setattr(mqtt_mock, "async_publish", publish)
    action = asyncio.create_task(
        hass.services.async_call(
            "cover", service, {"entity_id": cover_id, **data}, blocking=True
        )
    )
    try:
        await asyncio.wait_for(publish_started.wait(), timeout=5)
        assert not action.done()
        await hass.services.async_call(
            "cover", "stop_cover_tilt", {"entity_id": cover_id}, blocking=True
        )
        assert not action.done()
        assert publish.await_args_list == [
            call(f"{BASE_TOPIC}/cmd", payload, 2, False, message_expiry_interval=None),
            call(f"{BASE_TOPIC}/cmd", "stop", 2, False, message_expiry_interval=None),
            call(f"{BASE_TOPIC}/cmd", "stop", 2, False, message_expiry_interval=None),
        ]
        assert cover._requested_position == -1
        assert cover.current_cover_tilt_position is None
    finally:
        publish_completed.set()
        await action

    assert cover._requested_position == -1
    assert cover.current_cover_tilt_position is None
    assert publish.await_count == 3


async def test_one_percent_is_an_open_target(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient, cover_id: str
) -> None:
    """Publish the minimum open target through HA's native tilt service."""
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


@pytest.mark.parametrize("segment", ["", "unprefixed_serial", "%"])
async def test_invalid_discovery_segment_does_not_create_a_device(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    smarwi_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    dispatcher_spy: Mock,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    segment: str,
) -> None:
    """Require the documented percent marker and a nonempty serial segment."""
    devices = hass.data[DOMAIN][smarwi_entry.entry_id]
    previous_devices = devices.copy()
    constructor_spy = Mock(wraps=SmarwiDevice)
    monkeypatch.setattr("custom_components.smarwi.SmarwiDevice", constructor_spy)
    dispatcher_spy.reset_mock()
    caplog.clear()
    async_fire_mqtt_message(hass, f"ion/{REMOTE_ID}/{segment}/online", "1")
    await hass.async_block_till_done()
    assert devices == previous_devices
    constructor_spy.assert_not_called()
    dispatcher_spy.assert_not_called()
    assert all(record.levelno < logging.ERROR for record in caplog.records)
    mqtt_mock.async_publish.assert_not_called()

    serial = "offline_discovery_recovery"
    topic = f"ion/{REMOTE_ID}/%{serial}"
    async_fire_mqtt_message(hass, f"{topic}/online", "1")
    await hass.async_block_till_done()
    async_fire_mqtt_message(hass, f"{topic}/status", STATUS)
    await hass.async_block_till_done()
    assert serial in devices
    assert entity_registry.async_get_entity_id("cover", DOMAIN, f"{serial}_cover")
    constructor_spy.assert_called_once()
    mqtt_mock.async_publish.assert_not_called()
    async_fire_mqtt_message(hass, f"{topic}/online", "1")
    await hass.async_block_till_done()
    constructor_spy.assert_called_once()
    mqtt_mock.async_publish.assert_called_once_with(
        f"{topic}/cmd", "lcfa", 2, False, message_expiry_interval=None
    )


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


@pytest.mark.parametrize(
    ("position", "closed", "expected_state"),
    [
        ("c", True, "closed"),
        ("o", False, "open"),
        (None, None, "unknown"),
        ("", None, "unknown"),
        ("future", None, "unknown"),
        ("C", None, "unknown"),
        ("O", None, "unknown"),
    ],
)
async def test_position_telemetry_preserves_unknown_and_recovers(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    smarwi_entry: MockConfigEntry,
    cover_id: str,
    position: str | None,
    closed: bool | None,
    expected_state: str,
) -> None:
    """Interpret only literal c/o through public MQTT, without discarding status."""
    device: SmarwiDevice = hass.data[DOMAIN][smarwi_entry.entry_id][DEVICE_ID]
    async_fire_mqtt_message(
        hass, f"{BASE_TOPIC}/status", STATUS.replace("pos:o", "pos:c")
    )
    await hass.async_block_till_done()
    initial = hass.states.get(cover_id)
    assert initial is not None
    assert initial.attributes[ATTR_CURRENT_TILT_POSITION] == 0
    snapshot = {
        SmarwiDeviceProp.NAME: "Position fixture",
        SmarwiDeviceProp.RIDGE_FIXED: "1",
        SmarwiDeviceProp.RIDGE_INSIDE: "0",
        SmarwiDeviceProp.STATE_CODE: "250",
    }
    if position is not None:
        snapshot[SmarwiDeviceProp.CLOSED] = position
    payload = "\n".join(f"{key.value}:{value}" for key, value in snapshot.items())
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", payload)
    await hass.async_block_till_done()
    assert device._status == snapshot
    assert device.closed is closed
    state = hass.states.get(cover_id)
    assert state is not None
    assert state.state == expected_state
    assert state.attributes.get(ATTR_CURRENT_TILT_POSITION) == (
        0 if closed is True else None
    )
    assert state.attributes["state_code"] == "IDLE"
    assert device.available
    assert ATTR_CURRENT_POSITION not in state.attributes

    for known_position, known_closed, known_state in (
        ("c", True, "closed"),
        ("o", False, "open"),
    ):
        async_fire_mqtt_message(
            hass,
            f"{BASE_TOPIC}/status",
            STATUS.replace("pos:o", f"pos:{known_position}"),
        )
        await hass.async_block_till_done()
        assert device.closed is known_closed
        state = hass.states.get(cover_id)
        assert state is not None
        assert state.state == known_state
        assert state.attributes.get(ATTR_CURRENT_TILT_POSITION) == (
            0 if known_closed else None
        )

    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", payload)
    await hass.async_block_till_done()
    assert device._status == snapshot
    assert device.closed is closed
    state = hass.states.get(cover_id)
    assert state is not None
    assert state.state == expected_state
    assert state.attributes.get(ATTR_CURRENT_TILT_POSITION) == (
        0 if closed is True else None
    )
    mqtt_mock.async_publish.assert_not_called()


@pytest.mark.parametrize("target", [30, 100])
async def test_near_frame_and_requested_target_are_not_tilt_feedback(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient, cover_id: str, target: int
) -> None:
    """Keep inherited near-frame and idle target estimates out of public state."""
    for code in (200, 250):
        async_fire_mqtt_message(
            hass, f"{BASE_TOPIC}/status", STATUS.replace("s:250", f"s:{code}")
        )
        await hass.async_block_till_done()
        state = hass.states.get(cover_id)
        assert state is not None
        assert ATTR_CURRENT_TILT_POSITION not in state.attributes
    await hass.services.async_call(
        "cover",
        "set_cover_tilt_position",
        {"entity_id": cover_id, ATTR_TILT_POSITION: target},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(
        f"{BASE_TOPIC}/cmd", f"open;{target}", 2, False, message_expiry_interval=None
    )
    for code in (210, 250):
        async_fire_mqtt_message(
            hass, f"{BASE_TOPIC}/status", STATUS.replace("s:250", f"s:{code}")
        )
        await hass.async_block_till_done()
        state = hass.states.get(cover_id)
        assert state is not None
        assert ATTR_CURRENT_TILT_POSITION not in state.attributes
        assert ATTR_CURRENT_POSITION not in state.attributes


async def test_close_request_without_closed_telemetry_does_not_report_zero(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient, cover_id: str
) -> None:
    """A close target and idle transition do not establish observed closure."""
    await hass.services.async_call(
        "cover", "close_cover_tilt", {"entity_id": cover_id}, blocking=True
    )
    mqtt_mock.async_publish.assert_called_once_with(
        f"{BASE_TOPIC}/cmd", "close", 2, False, message_expiry_interval=None
    )
    for code in (220, 250):
        async_fire_mqtt_message(
            hass, f"{BASE_TOPIC}/status", STATUS.replace("s:250", f"s:{code}")
        )
        await hass.async_block_till_done()
        state = hass.states.get(cover_id)
        assert state is not None
        assert ATTR_CURRENT_TILT_POSITION not in state.attributes
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
    assert ATTR_CURRENT_TILT_POSITION not in state.attributes
    cover = next(
        entity
        for platform in async_get_platforms(hass, DOMAIN)
        for entity in platform.entities.values()
        if entity.entity_id == cover_id
    )
    assert isinstance(cover, SmarwiCover)
    assert cover._position == 30
    await hass.services.async_call(
        "cover",
        "set_cover_tilt_position",
        {"entity_id": cover_id, ATTR_TILT_POSITION: 100},
        blocking=True,
    )

    async_fire_mqtt_message(
        hass, f"{BASE_TOPIC}/status", STATUS.replace("s:250", "s:210")
    )
    await hass.async_block_till_done()
    state = hass.states.get(cover_id)
    assert state is not None
    assert state.state == "opening"
    assert cover._position == 30
    assert cover._requested_position == 100
    assert cover.device.state_code.is_moving()
    assert cover.current_cover_tilt_position is None
    mqtt_mock.async_publish.reset_mock()
    await hass.services.async_call(
        "cover", "stop_cover_tilt", {"entity_id": cover_id}, blocking=True
    )
    assert mqtt_mock.async_publish.call_args_list == [
        call(f"{BASE_TOPIC}/cmd", "stop", 2, False, message_expiry_interval=None),
        call(f"{BASE_TOPIC}/cmd", "stop", 2, False, message_expiry_interval=None),
    ]
    assert cover._position == -1
    assert cover._requested_position == -1
    # The inherited entity writes HA state on telemetry, not immediately on Stop.
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", STATUS)
    await hass.async_block_till_done()
    state = hass.states.get(cover_id)
    assert state is not None
    assert ATTR_CURRENT_TILT_POSITION not in state.attributes
    assert ATTR_CURRENT_POSITION not in state.attributes


async def test_status_with_empty_lines_updates_the_cover(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient, cover_id: str
) -> None:
    """Decode a whole synthetic status despite leading/internal/trailing blanks."""
    payload = "\n" + STATUS.replace("pos:o", "pos:c").replace("\n", "\n\n") + "\n\n"
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", payload)
    await hass.async_block_till_done()
    state = hass.states.get(cover_id)
    assert state is not None
    assert state.state == "closed"
    assert state.attributes[ATTR_CURRENT_TILT_POSITION] == 0
    mqtt_mock.async_publish.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "\n\n",
        "future:present",
        STATUS.replace("pos:o", "pos:c") + "\nbroken",
        "broken\n" + STATUS.replace("pos:o", "pos:c"),
        STATUS.replace("pos:o", "pos:c") + "\n ",
    ],
)
async def test_invalid_status_preserves_the_previous_snapshot(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    smarwi_entry: MockConfigEntry,
    cover_id: str,
    caplog: pytest.LogCaptureFixture,
    dispatcher_spy: Mock,
    payload: str,
) -> None:
    """Reject the entire message, without refreshing old data or publishing."""
    device: SmarwiDevice = hass.data[DOMAIN][smarwi_entry.entry_id][DEVICE_ID]
    snapshot = device._status.copy()
    previous_state = hass.states.get(cover_id)
    dispatcher_spy.reset_mock()
    caplog.clear()
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", payload)
    await hass.async_block_till_done()
    dispatcher_spy.assert_not_called()
    assert device._status == snapshot
    assert hass.states.get(cover_id) is previous_state
    assert all(record.levelno < logging.ERROR for record in caplog.records)
    mqtt_mock.async_publish.assert_not_called()

    async_fire_mqtt_message(
        hass, f"{BASE_TOPIC}/status", STATUS.replace("pos:o", "pos:c")
    )
    await hass.async_block_till_done()
    state = hass.states.get(cover_id)
    assert state is not None
    assert state.state == "closed"


@pytest.mark.parametrize("payload", ["", "\n\n", "future:present", "s:250\nbroken"])
async def test_invalid_initial_status_does_not_register_a_cover(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    smarwi_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    caplog: pytest.LogCaptureFixture,
    dispatcher_spy: Mock,
    payload: str,
) -> None:
    """Do not announce entities until there is a nonempty recognized status."""
    serial = "offline_uninitialized"
    topic = f"ion/{REMOTE_ID}/%{serial}"
    async_fire_mqtt_message(hass, f"{topic}/online", "1")
    await hass.async_block_till_done()
    mqtt_mock.async_publish.reset_mock()
    dispatcher_spy.reset_mock()
    caplog.clear()
    async_fire_mqtt_message(hass, f"{topic}/status", payload)
    await hass.async_block_till_done()
    dispatcher_spy.assert_not_called()
    device: SmarwiDevice = hass.data[DOMAIN][smarwi_entry.entry_id][serial]
    assert device._status == {}
    assert (
        entity_registry.async_get_entity_id("cover", DOMAIN, f"{serial}_cover") is None
    )
    assert all(record.levelno < logging.ERROR for record in caplog.records)
    mqtt_mock.async_publish.assert_not_called()

    async_fire_mqtt_message(hass, f"{topic}/status", STATUS)
    await hass.async_block_till_done()
    assert entity_registry.async_get_entity_id("cover", DOMAIN, f"{serial}_cover")


@pytest.mark.parametrize("initial", [True, False], ids=["initial", "registered"])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ip", "invalid"),
        ("ip", ""),
        ("ip", "-1"),
        ("ip", "4294967296"),
        ("rssi", "invalid"),
        ("rssi", ""),
        ("s", "invalid"),
    ],
)
async def test_invalid_numeric_status_is_atomic(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    smarwi_entry: MockConfigEntry,
    cover_id: str,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    caplog: pytest.LogCaptureFixture,
    dispatcher_spy: Mock,
    monkeypatch: pytest.MonkeyPatch,
    initial: bool,
    field: str,
    value: str,
) -> None:
    """Reject bad numbers before discovery, registry work or any state write."""
    serial = "offline_numeric_initial" if initial else DEVICE_ID
    topic = f"ion/{REMOTE_ID}/%{serial}"
    if initial:
        async_fire_mqtt_message(hass, f"{topic}/online", "1")
        await hass.async_block_till_done()
    else:
        assert device_registry.async_get_device_by_identifier(
            (DOMAIN, serial), smarwi_entry.entry_id
        )
    device: SmarwiDevice = hass.data[DOMAIN][smarwi_entry.entry_id][serial]
    snapshot = device._status
    previous_values = snapshot.copy()
    previous_state = hass.states.get(cover_id)
    registry_spy = AsyncMock(wraps=device._async_update_device_registry)
    monkeypatch.setattr(device, "_async_update_device_registry", registry_spy)
    registry_write_spy = Mock(wraps=device_registry.async_update_device)
    monkeypatch.setattr(device_registry, "async_update_device", registry_write_spy)
    real_state_write = Entity.async_write_ha_state
    state_write_spy = Mock()
    monkeypatch.setattr(Entity, "async_write_ha_state", state_write_spy)
    mqtt_mock.async_publish.reset_mock()
    dispatcher_spy.reset_mock()
    caplog.clear()
    payload = STATUS.replace("pos:o", "pos:c") + "\nip:67305985\nrssi:-63"
    payload = payload.replace("Offline fixture", "Rejected numeric fixture")
    payload = "\n".join(
        f"{field}:{value}" if line.startswith(f"{field}:") else line
        for line in payload.splitlines()
    )
    async_fire_mqtt_message(hass, f"{topic}/status", payload)
    await hass.async_block_till_done()
    assert device._status is snapshot
    assert device._status == previous_values
    dispatcher_spy.assert_not_called()
    registry_spy.assert_not_called()
    registry_write_spy.assert_not_called()
    state_write_spy.assert_not_called()
    assert hass.states.get(cover_id) is previous_state
    if initial:
        assert snapshot == {}
        assert (
            entity_registry.async_get_entity_id("cover", DOMAIN, f"{serial}_cover")
            is None
        )
        assert (
            device_registry.async_get_device_by_identifier(
                (DOMAIN, serial), smarwi_entry.entry_id
            )
            is None
        )
    assert all(record.levelno < logging.ERROR for record in caplog.records)
    assert any(
        "Ignoring malformed SMARWI status message" in r.message for r in caplog.records
    )
    assert all(
        "Rejected numeric fixture" not in r.message
        for r in caplog.records
        if r.name.startswith("custom_components.smarwi")
    )
    mqtt_mock.async_publish.assert_not_called()

    # Restore real writes so recovery is observable in HA, not just the snapshot.
    monkeypatch.setattr(Entity, "async_write_ha_state", real_state_write)
    async_fire_mqtt_message(
        hass, f"{topic}/status", STATUS.replace("pos:o", "pos:c") + "\nip:67305985"
    )
    await hass.async_block_till_done()
    assert device._status is not snapshot
    assert device.ip_address == "1.2.3.4"
    recovered_id = entity_registry.async_get_entity_id(
        "cover", DOMAIN, f"{serial}_cover"
    )
    assert recovered_id is not None
    registry_spy.assert_awaited_once()
    if initial:
        assert dispatcher_spy.call_count == 2
    else:
        recovered_state = hass.states.get(recovered_id)
        assert recovered_state is not None
        assert recovered_state.state == "closed"
        registry_write_spy.assert_called_once()
        dispatcher_spy.assert_called_once()
    mqtt_mock.async_publish.assert_not_called()


@pytest.mark.parametrize(
    ("ip", "address", "rssi", "state", "expected_state"),
    [
        ("0", "0.0.0.0", "-63", "250", StateCode.IDLE),
        ("4294967295", "255.255.255.255", "+1", "999", StateCode.UNKNOWN),
        (" +67305985 ", "1.2.3.4", " -63 ", " +250 ", StateCode.IDLE),
        ("67305985", "1.2.3.4", "1_0", "", StateCode.UNKNOWN),
        ("67305985", "1.2.3.4", "0", "-1", StateCode.UNKNOWN),
    ],
)
async def test_numeric_status_preserves_existing_conversions(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    smarwi_entry: MockConfigEntry,
    dispatcher_spy: Mock,
    ip: str,
    address: str,
    rssi: str,
    state: str,
    expected_state: StateCode,
) -> None:
    """Keep int syntax, unsigned IP endpoints, byte order and unknown states."""
    device: SmarwiDevice = hass.data[DOMAIN][smarwi_entry.entry_id][DEVICE_ID]
    dispatcher_spy.reset_mock()
    payload = STATUS.replace("s:250", f"s:{state}") + f"\nip:{ip}\nrssi:{rssi}"
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", payload)
    await hass.async_block_till_done()
    assert device.ip_address == address
    assert device.rssi == int(rssi)
    assert device.state_code is expected_state
    assert device._status[SmarwiDeviceProp.IP_ADDRESS] == ip
    assert device._status[SmarwiDeviceProp.RSSI] == rssi
    assert device._status[SmarwiDeviceProp.STATE_CODE] == state
    dispatcher_spy.assert_called_once()
    mqtt_mock.async_publish.assert_not_called()


async def test_partial_status_replaces_numeric_fields_with_defaults(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    smarwi_entry: MockConfigEntry,
    dispatcher_spy: Mock,
) -> None:
    """Missing numbers remain optional; accepted partial statuses do not merge."""
    device: SmarwiDevice = hass.data[DOMAIN][smarwi_entry.entry_id][DEVICE_ID]
    async_fire_mqtt_message(
        hass, f"{BASE_TOPIC}/status", STATUS + "\nip:67305985\nrssi:-63"
    )
    await hass.async_block_till_done()
    dispatcher_spy.reset_mock()
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", "pos:c")
    await hass.async_block_till_done()
    assert device._status == {SmarwiDeviceProp.CLOSED: "c"}
    assert device.ip_address is None
    assert device.rssi is None
    assert device.state_code is StateCode.UNKNOWN
    dispatcher_spy.assert_called_once()
    mqtt_mock.async_publish.assert_not_called()


async def test_advanced_config_with_empty_lines_is_decoded(
    hass: HomeAssistant, mqtt_mock: MqttMockHAClient, smarwi_entry: MockConfigEntry
) -> None:
    """Protect the shared decoder's second caller without writing settings."""
    async_fire_mqtt_message(
        hass,
        f"{BASE_TOPIC}/config/advanced",
        "\nvpct:80\n\nospd:40\nfuture:7\ncvdist:1234\n\n",
    )
    await hass.async_block_till_done()
    device: SmarwiDevice = hass.data[DOMAIN][smarwi_entry.entry_id][DEVICE_ID]
    assert device.finetune_settings._data == {"vpct": 80, "ospd": 40, "future": 7}
    mqtt_mock.async_publish.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "\n\n",
        "cvdist:1234",
        "vpct:20\nbroken",
        "broken\nvpct:20",
        "vpct:20\nospd:invalid",
    ],
)
async def test_invalid_advanced_config_preserves_the_previous_snapshot(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    smarwi_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    dispatcher_spy: Mock,
    payload: str,
) -> None:
    """Reject invalid settings before replacing any previously received values."""
    async_fire_mqtt_message(
        hass, f"{BASE_TOPIC}/config/advanced", "vpct:80\nospd:40\nfuture:7"
    )
    await hass.async_block_till_done()
    device: SmarwiDevice = hass.data[DOMAIN][smarwi_entry.entry_id][DEVICE_ID]
    snapshot = device.finetune_settings._data.copy()
    assert snapshot == {"vpct": 80, "ospd": 40, "future": 7}
    dispatcher_spy.reset_mock()
    caplog.clear()
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/config/advanced", payload)
    await hass.async_block_till_done()
    dispatcher_spy.assert_not_called()
    assert device.finetune_settings._data == snapshot
    assert all(record.levelno < logging.ERROR for record in caplog.records)
    mqtt_mock.async_publish.assert_not_called()

    async_fire_mqtt_message(
        hass, f"{BASE_TOPIC}/config/advanced", "vpct:75\nospd:30\nfuture:8"
    )
    await hass.async_block_till_done()
    assert device.finetune_settings._data == {"vpct": 75, "ospd": 30, "future": 8}


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


@pytest.mark.parametrize("reconnect", [False, True])
async def test_broker_session_does_not_reuse_online(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    smarwi_entry: MockConfigEntry,
    cover_id: str,
    broker_connection: Mock,
    reconnect: bool,
) -> None:
    """Disconnect and reconnect-only must not leave cached entities available."""
    state = hass.states.get(cover_id)
    assert state is not None
    assert state.state == "open"
    broker_connection(False)
    await hass.async_block_till_done()
    if reconnect:
        broker_connection(True)
        await hass.async_block_till_done()
    state = hass.states.get(cover_id)
    assert state is not None
    assert state.state == "unavailable"
    mqtt_mock.async_publish.assert_not_called()


@pytest.mark.parametrize("online_first", [False, True])
async def test_broker_availability_requires_accepted_status(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    online_first: bool,
) -> None:
    """Neither online nor malformed status substitutes for accepted telemetry."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_REMOTE_ID: REMOTE_ID})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/online", "1")
    await hass.async_block_till_done()
    device = hass.data[DOMAIN][entry.entry_id][DEVICE_ID]
    if online_first:
        async_fire_mqtt_message(hass, f"{BASE_TOPIC}/online", "1")
        await hass.async_block_till_done()
    for payload in ("broken", "s:bad", "future:1", ""):
        async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", payload)
        await hass.async_block_till_done()
        assert not device.available
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", STATUS)
    await hass.async_block_till_done()
    assert device.available is online_first
    if not online_first:
        async_fire_mqtt_message(hass, f"{BASE_TOPIC}/online", "1")
        await hass.async_block_till_done()
    assert device.available


@pytest.mark.parametrize("retained_online", [False, True])
async def test_broker_session_recovery_preserves_last_known_cache(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    smarwi_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    broker_connection: Mock,
    dispatcher_spy: Mock,
    retained_online: bool,
) -> None:
    """New-session online, including retained replay, is observation not freshness."""
    second_id = "offline_second_serial"
    second_topic = f"ion/{REMOTE_ID}/%{second_id}"
    for topic, payload in (
        (f"{second_topic}/online", "1"),
        (f"{second_topic}/status", STATUS.replace("Offline fixture", "Second fixture")),
        (f"{second_topic}/online", "1"),
        (f"{BASE_TOPIC}/config/advanced", "vpct:75\nospd:30"),
        (f"{second_topic}/config/advanced", "vpct:75\nospd:30"),
    ):
        async_fire_mqtt_message(hass, topic, payload)
        await hass.async_block_till_done()
    devices = hass.data[DOMAIN][smarwi_entry.entry_id]
    snapshots = {
        key: (device._status.copy(), device.finetune_settings._data.copy())
        for key, device in devices.items()
    }
    entity_ids = []
    for device_id in (DEVICE_ID, second_id):
        for platform, key in (
            ("cover", "cover"),
            ("binary_sensor", "ridge_inside"),
            ("switch", "ridge_fix"),
            ("number", "max_open_position"),
        ):
            entity_id = entity_registry.async_get_entity_id(
                platform, DOMAIN, f"{device_id}_{key}"
            )
            assert entity_id is not None
            state = hass.states.get(entity_id)
            assert state is not None
            assert state.state != "unavailable"
            entity_ids.append(entity_id)

    mqtt_mock.async_publish.reset_mock()
    dispatcher_spy.reset_mock()
    broker_connection(False)
    await hass.async_block_till_done()
    for device in devices.values():
        dispatcher_spy.assert_any_call(
            hass, device.signal_update, {SmarwiDeviceProp.AVAILABLE}
        )
        assert not device.available
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == "unavailable"
    for topic in (BASE_TOPIC, second_topic):
        # HA's message injector can simulate a queued online arriving after loss.
        async_fire_mqtt_message(hass, f"{topic}/online", "1")
        await hass.async_block_till_done()
    mqtt_mock.async_publish.assert_not_called()
    for _ in range(2):
        broker_connection(True)
        await hass.async_block_till_done()
        for entity_id in entity_ids:
            state = hass.states.get(entity_id)
            assert state is not None
            assert state.state == "unavailable"
    mqtt_mock.async_publish.assert_not_called()
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", STATUS)
    await hass.async_block_till_done()
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == "unavailable"
    for topic in (BASE_TOPIC, second_topic):
        async_fire_mqtt_message(hass, f"{topic}/online", "0")
        await hass.async_block_till_done()
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == "unavailable"
    # Existing online handling requests lcfa even for online=0; not new traffic.
    assert mqtt_mock.async_publish.call_count == 2
    mqtt_mock.async_publish.reset_mock()
    for topic in (BASE_TOPIC, second_topic):
        async_fire_mqtt_message(hass, f"{topic}/online", "1", retain=retained_online)
        await hass.async_block_till_done()
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state != "unavailable"
    assert mqtt_mock.async_publish.call_args_list == [
        call(f"{BASE_TOPIC}/cmd", "lcfa", 2, False, message_expiry_interval=None),
        call(f"{second_topic}/cmd", "lcfa", 2, False, message_expiry_interval=None),
    ]
    for key, device in devices.items():
        assert (device._status, device.finetune_settings._data) == snapshots[key]
        assert device.closed is False
        assert device.state_code is StateCode.IDLE

    assert await hass.config_entries.async_unload(smarwi_entry.entry_id)
    await hass.async_block_till_done()
    unloaded_states = {
        entity_id: hass.states.get(entity_id) for entity_id in entity_ids
    }
    dispatcher_spy.reset_mock()
    mqtt_mock.async_publish.reset_mock()
    mqtt_mock.async_subscribe.reset_mock()
    broker_connection(False)
    await hass.async_block_till_done()
    broker_connection(True)
    await hass.async_block_till_done()
    for topic in (BASE_TOPIC, second_topic):
        async_fire_mqtt_message(hass, f"{topic}/online", "1")
        async_fire_mqtt_message(hass, f"{topic}/status", STATUS)
    await hass.async_block_till_done()
    dispatcher_spy.assert_not_called()
    mqtt_mock.async_publish.assert_not_called()
    mqtt_mock.async_subscribe.assert_not_called()
    assert smarwi_entry.entry_id not in hass.data[DOMAIN]
    assert {
        entity_id: hass.states.get(entity_id) for entity_id in entity_ids
    } == unloaded_states


async def test_broker_disconnected_discovery_cannot_arm_online(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    broker_connection: Mock,
) -> None:
    """Devices created while disconnected also require a connected online message."""
    broker_connection(False)
    await hass.async_block_till_done()
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_REMOTE_ID: REMOTE_ID})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    for suffix, payload in (("online", "1"), ("online", "1"), ("status", STATUS)):
        async_fire_mqtt_message(hass, f"{BASE_TOPIC}/{suffix}", payload)
        await hass.async_block_till_done()
    device = hass.data[DOMAIN][entry.entry_id][DEVICE_ID]
    assert not device.available
    mqtt_mock.async_publish.assert_not_called()
    broker_connection(True)
    await hass.async_block_till_done()
    assert not device.available
    mqtt_mock.async_publish.assert_not_called()
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/online", "1")
    await hass.async_block_till_done()
    assert device.available
