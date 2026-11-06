"""Public HA setup and tilt-service tests with an entirely mocked MQTT client."""

import asyncio
from collections.abc import Callable, Coroutine, Iterable
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
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceNotSupported
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import async_get_platforms

from custom_components.smarwi.const import CONF_REMOTE_ID, DOMAIN
from custom_components.smarwi.cover import SmarwiCover
from custom_components.smarwi.device import (
    SmarwiConfigEntry,
    SmarwiDevice,
    SmarwiDeviceProp,
    StateCode,
)
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


async def test_runtime_data_is_entry_owned_before_platform_setup(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    entity_registry: er.EntityRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Give each entry its own cache before forwarding all five real platforms."""
    forward = hass.config_entries.async_forward_entry_setups
    caches: list[dict[str, SmarwiDevice] | None] = []

    async def check_runtime(
        entry: SmarwiConfigEntry, platforms: Iterable[Platform | str]
    ) -> None:
        cache = getattr(entry, "runtime_data", None)
        caches.append(cache)
        await forward(entry, platforms)

    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", check_runtime
    )
    entries: list[MockConfigEntry] = []
    for remote in (REMOTE_ID, "offline_other_remote"):
        entry = MockConfigEntry(domain=DOMAIN, data={CONF_REMOTE_ID: remote})
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entries.append(entry)
    assert caches == [{}, {}]
    assert caches[0] is not caches[1]
    assert DOMAIN not in hass.data

    for index, entry in enumerate(entries):
        serial = f"runtime_serial_{index}"
        topic = f"ion/{entry.data[CONF_REMOTE_ID]}/%{serial}"
        for suffix, payload in (("online", "1"), ("status", STATUS)):
            async_fire_mqtt_message(hass, f"{topic}/{suffix}", payload)
            await hass.async_block_till_done()
        assert set(entry.runtime_data) == {serial}
        assert entry.runtime_data is caches[index]
        registered = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        assert {item.domain for item in registered} == {
            "binary_sensor",
            "cover",
            "number",
            "sensor",
            "switch",
        }
        assert all(item.unique_id.startswith(f"{serial}_") for item in registered)
    assert await hass.config_entries.async_unload(entries[0].entry_id)
    assert getattr(entries[0], "runtime_data", None) is None
    assert entries[1].runtime_data is caches[1]
    assert set(entries[1].runtime_data) == {"runtime_serial_1"}


async def test_runtime_data_reload_replaces_cache_without_duplicate_devices(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    smarwi_entry: MockConfigEntry,
    cover_id: str,
    broker_connection: Mock,
    dispatcher_spy: Mock,
) -> None:
    """Native reload replaces the cache and removes old transport listeners."""
    old_cache = getattr(smarwi_entry, "runtime_data", None)
    assert isinstance(old_cache, dict)
    old_device = old_cache[DEVICE_ID]
    assert await hass.config_entries.async_reload(smarwi_entry.entry_id)
    await hass.async_block_till_done()
    assert smarwi_entry.runtime_data == {}
    assert smarwi_entry.runtime_data is not old_cache
    dispatcher_spy.reset_mock()
    broker_connection(False)
    await hass.async_block_till_done()
    dispatcher_spy.assert_not_called()
    broker_connection(True)
    await hass.async_block_till_done()
    for suffix, payload in (("online", "1"), ("status", STATUS), ("online", "1")):
        async_fire_mqtt_message(hass, f"{BASE_TOPIC}/{suffix}", payload)
        await hass.async_block_till_done()
    device = smarwi_entry.runtime_data[DEVICE_ID]
    assert device is not old_device
    assert old_device._status is not device._status
    assert len(smarwi_entry.runtime_data) == 1
    state = hass.states.get(cover_id)
    assert state is not None
    assert state.state == "open"
    dispatcher_spy.reset_mock()
    mqtt_mock.async_publish.reset_mock()
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/online", "0")
    await hass.async_block_till_done()
    assert dispatcher_spy.call_count == 1
    mqtt_mock.async_publish.assert_called_once_with(
        f"{BASE_TOPIC}/cmd", "lcfa", 2, False, message_expiry_interval=None
    )


async def test_runtime_data_failed_unload_keeps_active_cache(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    smarwi_entry: MockConfigEntry,
    cover_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rejected platform unload must not discard data or subscriptions."""
    cache = getattr(smarwi_entry, "runtime_data", None)
    assert isinstance(cache, dict)
    device = cache[DEVICE_ID]
    with monkeypatch.context() as patch:
        patch.setattr(
            hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False)
        )
        assert not await hass.config_entries.async_unload(smarwi_entry.entry_id)
    assert smarwi_entry.state is ConfigEntryState.FAILED_UNLOAD
    assert smarwi_entry.runtime_data is cache
    async_fire_mqtt_message(
        hass, f"{BASE_TOPIC}/status", STATUS.replace("pos:o", "pos:c")
    )
    await hass.async_block_till_done()
    assert cache[DEVICE_ID] is device
    assert device.closed is True
    state = hass.states.get(cover_id)
    assert state is not None
    assert state.state == "closed"
    mqtt_mock.async_publish.assert_not_called()


async def test_runtime_data_setup_failure_retry_preserves_other_entry(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    smarwi_entry: MockConfigEntry,
    broker_connection: Mock,
    dispatcher_spy: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native setup failure cleans listeners; retry cannot disturb a loaded entry."""
    active_cache = getattr(smarwi_entry, "runtime_data", None)
    assert isinstance(active_cache, dict)
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_REMOTE_ID: "offline_other_remote"}
    )
    entry.add_to_hass(hass)
    subscribe = mqtt.async_subscribe_connection_status
    cleanups: list[Mock] = []

    def track_subscription(
        hass: HomeAssistant, listener: Callable[[bool], None]
    ) -> Mock:
        cleanup = Mock(wraps=subscribe(hass, listener))
        cleanups.append(cleanup)
        return cleanup

    monkeypatch.setattr(mqtt, "async_subscribe_connection_status", track_subscription)
    with monkeypatch.context() as patch:
        patch.setattr(
            hass.config_entries,
            "async_forward_entry_setups",
            AsyncMock(side_effect=RuntimeError("Synthetic forwarding failure")),
        )
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert len(cleanups) == 1
    cleanups[0].assert_called_once_with()
    failed_cache = entry.runtime_data
    assert failed_cache == {}
    assert smarwi_entry.runtime_data is active_cache
    dispatcher_spy.reset_mock()
    broker_connection(False)
    await hass.async_block_till_done()
    assert dispatcher_spy.call_count == 1
    broker_connection(True)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data == {}
    assert entry.runtime_data is not failed_cache
    assert len(cleanups) == 2
    cleanups[1].assert_not_called()
    assert smarwi_entry.runtime_data is active_cache
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert getattr(entry, "runtime_data", None) is None
    cleanups[0].assert_called_once_with()
    cleanups[1].assert_called_once_with()
    assert smarwi_entry.runtime_data is active_cache
    assert DOMAIN not in hass.data


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

        device: SmarwiDevice = entry.runtime_data[DEVICE_ID]
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
    devices = smarwi_entry.runtime_data
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
    device: SmarwiDevice = smarwi_entry.runtime_data[DEVICE_ID]
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
    device: SmarwiDevice = smarwi_entry.runtime_data[DEVICE_ID]
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
    device: SmarwiDevice = smarwi_entry.runtime_data[serial]
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
    device: SmarwiDevice = smarwi_entry.runtime_data[serial]
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
    device: SmarwiDevice = smarwi_entry.runtime_data[DEVICE_ID]
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
    device: SmarwiDevice = smarwi_entry.runtime_data[DEVICE_ID]
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
    device: SmarwiDevice = smarwi_entry.runtime_data[DEVICE_ID]
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
    device: SmarwiDevice = smarwi_entry.runtime_data[DEVICE_ID]
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
    device = entry.runtime_data[DEVICE_ID]
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
    devices = smarwi_entry.runtime_data
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
    assert getattr(smarwi_entry, "runtime_data", None) is None
    assert DOMAIN not in hass.data
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
    device = entry.runtime_data[DEVICE_ID]
    assert not device.available
    mqtt_mock.async_publish.assert_not_called()
    broker_connection(True)
    await hass.async_block_till_done()
    assert not device.available
    mqtt_mock.async_publish.assert_not_called()
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/online", "1")
    await hass.async_block_till_done()
    assert device.available


@pytest.mark.parametrize(
    ("service", "data", "target", "payload"),
    [
        ("open_cover_tilt", {}, 100, "open;100"),
        ("close_cover_tilt", {}, 0, "close"),
        ("set_cover_tilt_position", {ATTR_TILT_POSITION: 30}, 30, "open;30"),
    ],
)
@pytest.mark.parametrize("flow", ["current", "broker_loss", "closed_idle"])
@pytest.mark.parametrize("cancelled", [False, True], ids=["failure", "cancellation"])
async def test_failed_tilt_service_cleans_only_owned_local_intent(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    cover_id: str,
    broker_connection: Mock,
    monkeypatch: pytest.MonkeyPatch,
    service: str,
    data: dict[str, int],
    target: int,
    payload: str,
    flow: str,
    cancelled: bool,
) -> None:
    """Propagate failed ACKs, preserving raw telemetry and newer closed zero."""
    cover = next(
        platform.entities[cover_id]
        for platform in async_get_platforms(hass, DOMAIN)
        if cover_id in platform.entities
    )
    assert isinstance(cover, SmarwiCover)
    async_fire_mqtt_message(
        hass, f"{BASE_TOPIC}/status", STATUS.replace("s:250", "s:200")
    )
    await hass.async_block_till_done()
    assert cover._position == 5
    assert cover._is_moving
    started = asyncio.Event()
    updated = asyncio.Event()
    original_update = cover.async_handle_update

    async def observe_update(props: set[SmarwiDeviceProp]) -> None:
        await original_update(props)
        updated.set()

    monkeypatch.setattr(cover, "async_handle_update", observe_update)
    result: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    async def pending(*args: object, **kwargs: object) -> None:
        started.set()
        await result

    publish = AsyncMock(side_effect=pending)
    monkeypatch.setattr(mqtt_mock, "async_publish", publish)
    action = asyncio.create_task(
        hass.services.async_call(
            "cover", service, {"entity_id": cover_id, **data}, blocking=True
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 5)
        assert not action.done()
        assert cover._requested_position == target
        owner = cover._intent_owner
        assert owner is not None
        if flow == "broker_loss":
            broker_connection(False)
            await asyncio.wait_for(updated.wait(), 5)
            assert not cover.available
            # Availability-only updates are not a new intent-invalidation policy.
            assert cover._intent_owner is owner
            assert cover._requested_position == target
        elif flow == "closed_idle":
            async_fire_mqtt_message(
                hass, f"{BASE_TOPIC}/status", STATUS.replace("pos:o", "pos:c")
            )
            await asyncio.wait_for(updated.wait(), 5)
            assert cover._requested_position == -1
            assert cover._position == 0
            assert cover._intent_owner is None
        snapshot = cover.device._status
        values = snapshot.copy()
        moving = cover._is_moving
        if cancelled:
            result.set_exception(asyncio.CancelledError("publish cancelled"))
            with pytest.raises(asyncio.CancelledError) as caught_cancel:
                await action
            assert caught_cancel.value.args == ("publish cancelled",)
        else:
            error = HomeAssistantError("publish failed after possible delivery")
            result.set_exception(error)
            with pytest.raises(HomeAssistantError) as caught_error:
                await action
            assert caught_error.value is error
        assert cover._requested_position == -1
        assert cover._position == (0 if flow == "closed_idle" else -1)
        assert cover._intent_owner is None
        assert cover.device._status is snapshot
        assert cover.device._status == values
        assert cover._is_moving is moving
        publish.assert_awaited_once_with(
            f"{BASE_TOPIC}/cmd", payload, 2, False, message_expiry_interval=None
        )
    finally:
        if not result.done():
            result.cancel()
        await asyncio.gather(action, return_exceptions=True)


@pytest.mark.parametrize(
    ("outcome", "service", "data", "target", "payload"),
    [
        ("success", "open_cover_tilt", {}, 100, "open;100"),
        ("failure", "close_cover_tilt", {}, 0, "close"),
        (
            "cancellation",
            "set_cover_tilt_position",
            {ATTR_TILT_POSITION: 30},
            30,
            "open;30",
        ),
    ],
)
@pytest.mark.parametrize("reload", [True, False], ids=["reload", "rejected_unload"])
async def test_pending_tilt_service_across_entry_unload(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    smarwi_entry: MockConfigEntry,
    cover_id: str,
    entity_registry: er.EntityRegistry,
    dispatcher_spy: Mock,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    service: str,
    data: dict[str, int],
    target: int,
    payload: str,
    reload: bool,
) -> None:
    """Late mocked publish results belong to the caller, not a replacement entity."""
    old_cache = smarwi_entry.runtime_data
    old_device = old_cache[DEVICE_ID]
    old_cover = next(
        platform.entities[cover_id]
        for platform in async_get_platforms(hass, DOMAIN)
        if cover_id in platform.entities
    )
    assert isinstance(old_cover, SmarwiCover)
    async_fire_mqtt_message(
        hass, f"{BASE_TOPIC}/status", STATUS.replace("s:250", "s:200")
    )
    await hass.async_block_till_done()
    assert old_cover._position == 5
    assert old_cover._is_moving
    old_status = old_device._status
    old_values = old_status.copy()
    old_updates = AsyncMock(wraps=old_cover.async_handle_update)
    monkeypatch.setattr(old_cover, "async_handle_update", old_updates)
    started = asyncio.Event()
    result: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    async def pending(
        topic: str, command: str, *args: object, **kwargs: object
    ) -> None:
        # Gate only the original command; rediscovery and replacement commands proceed.
        if topic == f"{BASE_TOPIC}/cmd" and command == payload and not started.is_set():
            started.set()
            await result

    publish = AsyncMock(side_effect=pending)
    monkeypatch.setattr(mqtt_mock, "async_publish", publish)
    action = asyncio.create_task(
        hass.services.async_call(
            "cover", service, {"entity_id": cover_id, **data}, blocking=True
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 5)
        assert not action.done()
        assert old_cover._requested_position == target
        owner = old_cover._intent_owner
        assert owner is not None
        publish.assert_awaited_once_with(
            f"{BASE_TOPIC}/cmd", payload, 2, False, message_expiry_interval=None
        )
        if reload:
            assert await asyncio.wait_for(
                hass.config_entries.async_unload(smarwi_entry.entry_id), 5
            )
            assert smarwi_entry.state is ConfigEntryState.NOT_LOADED
            assert getattr(smarwi_entry, "runtime_data", None) is None
            assert all(
                cover_id not in platform.entities
                for platform in async_get_platforms(hass, DOMAIN)
            )
            assert not action.done()
            assert await asyncio.wait_for(
                hass.config_entries.async_reload(smarwi_entry.entry_id), 5
            )
            assert smarwi_entry.state is ConfigEntryState.LOADED
            assert smarwi_entry.runtime_data == {}
            assert smarwi_entry.runtime_data is not old_cache
            initialized = asyncio.Event()
            attached = asyncio.Event()
            online = asyncio.Event()
            real_init = SmarwiDevice.async_init
            real_added = SmarwiCover.async_added_to_hass
            real_online = SmarwiDevice._async_handle_online_message

            async def observe_init(device: SmarwiDevice) -> None:
                await real_init(device)
                initialized.set()

            async def observe_added(cover: SmarwiCover) -> None:
                await real_added(cover)
                attached.set()

            async def observe_online(
                device: SmarwiDevice, msg: mqtt.ReceiveMessage
            ) -> None:
                await real_online(device, msg)
                online.set()

            monkeypatch.setattr(SmarwiDevice, "async_init", observe_init)
            monkeypatch.setattr(SmarwiCover, "async_added_to_hass", observe_added)
            monkeypatch.setattr(
                SmarwiDevice, "_async_handle_online_message", observe_online
            )
            async_fire_mqtt_message(hass, f"{BASE_TOPIC}/online", "1")
            await asyncio.wait_for(initialized.wait(), 5)
            async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", STATUS)
            await asyncio.wait_for(attached.wait(), 5)
            async_fire_mqtt_message(hass, f"{BASE_TOPIC}/online", "1")
            await asyncio.wait_for(online.wait(), 5)
        else:
            # Reject before any platform removal; partial unload failures are separate.
            with monkeypatch.context() as patch:
                patch.setattr(
                    hass.config_entries,
                    "async_unload_platforms",
                    AsyncMock(return_value=False),
                )
                assert not await asyncio.wait_for(
                    hass.config_entries.async_unload(smarwi_entry.entry_id), 5
                )
            assert smarwi_entry.state is ConfigEntryState.FAILED_UNLOAD
            assert smarwi_entry.runtime_data is old_cache

        covers = [
            platform.entities[cover_id]
            for platform in async_get_platforms(hass, DOMAIN)
            if cover_id in platform.entities
        ]
        assert len(covers) == 1
        cover = covers[0]
        assert isinstance(cover, SmarwiCover)
        cache = smarwi_entry.runtime_data
        device = cache[DEVICE_ID]
        assert set(cache) == {DEVICE_ID}
        assert cover.device is device
        assert (cover is not old_cover) is reload
        assert (device is not old_device) is reload
        assert (
            entity_registry.async_get_entity_id("cover", DOMAIN, f"{DEVICE_ID}_cover")
            == cover_id
        )
        assert not action.done()
        assert old_cover._intent_owner is owner
        assert old_cover._requested_position == target
        old_updates.assert_not_awaited()
        old_writes = Mock(wraps=old_cover.async_write_ha_state)
        monkeypatch.setattr(old_cover, "async_write_ha_state", old_writes)
        if reload:
            # Same target, new entity and owner: old cleanup must not clear this intent.
            await hass.services.async_call(
                "cover", service, {"entity_id": cover_id, **data}, blocking=True
            )
            assert cover._requested_position == target
            assert cover._intent_owner is not None
            assert cover._intent_owner is not owner
        replacement_owner = cover._intent_owner
        snapshot = device._status
        values = snapshot.copy()
        before = hass.states.get(cover_id)
        assert before is not None
        assert before.attributes["device_class"] == CoverDeviceClass.WINDOW
        assert before.attributes["supported_features"] == (
            CoverEntityFeature.OPEN_TILT
            | CoverEntityFeature.CLOSE_TILT
            | CoverEntityFeature.SET_TILT_POSITION
            | CoverEntityFeature.STOP_TILT
        )
        expected_publishes = [
            call(f"{BASE_TOPIC}/cmd", payload, 2, False, message_expiry_interval=None)
        ]
        if reload:
            expected_publishes += [
                call(
                    f"{BASE_TOPIC}/cmd", "lcfa", 2, False, message_expiry_interval=None
                ),
                call(
                    f"{BASE_TOPIC}/cmd", payload, 2, False, message_expiry_interval=None
                ),
            ]
        assert publish.await_args_list == expected_publishes
        if outcome == "success":
            result.set_result(None)
            await asyncio.wait_for(action, 5)
            assert old_cover._intent_owner is owner
            assert old_cover._requested_position == target
            assert old_cover._position == 5
        elif outcome == "failure":
            error = HomeAssistantError("publish failed after possible delivery")
            result.set_exception(error)
            with pytest.raises(HomeAssistantError) as caught_error:
                await asyncio.wait_for(action, 5)
            assert caught_error.value is error
        else:
            result.set_exception(asyncio.CancelledError("publish cancelled"))
            with pytest.raises(asyncio.CancelledError) as caught_cancel:
                await asyncio.wait_for(action, 5)
            assert caught_cancel.value.args == ("publish cancelled",)
        await hass.async_block_till_done()
        assert smarwi_entry.runtime_data is cache
        assert cache[DEVICE_ID] is device
        if outcome != "success":
            assert old_cover._intent_owner is None
            assert old_cover._requested_position == -1
            assert old_cover._position == -1
        assert old_cover._is_moving
        assert old_device._status is old_status
        assert old_device._status == old_values
        assert device._status is snapshot
        assert device._status == values
        assert hass.states.get(cover_id) is before
        old_writes.assert_not_called()
        old_updates.assert_not_awaited()
        if reload:
            assert cover._intent_owner is replacement_owner
            assert cover._requested_position == target
        updates = AsyncMock(wraps=cover.async_handle_update)
        writes = Mock(wraps=cover.async_write_ha_state)
        monkeypatch.setattr(cover, "async_handle_update", updates)
        monkeypatch.setattr(cover, "async_write_ha_state", writes)
        dispatcher_spy.reset_mock()
        async_fire_mqtt_message(
            hass, f"{BASE_TOPIC}/status", STATUS.replace("pos:o", "pos:c")
        )
        await hass.async_block_till_done()
        dispatcher_spy.assert_called_once_with(
            hass,
            device.signal_update,
            {SmarwiDeviceProp.CLOSED}
            | ({SmarwiDeviceProp.STATE_CODE} if not reload else set()),
        )
        updates.assert_awaited_once()
        writes.assert_called_once_with()
        after = hass.states.get(cover_id)
        assert after is not None and after.state == "closed"
        assert after.attributes[ATTR_CURRENT_TILT_POSITION] == 0
        if reload:
            old_updates.assert_not_awaited()
            old_writes.assert_not_called()
            assert old_device._status is old_status
        assert publish.await_args_list == expected_publishes
    finally:
        if not result.done():
            result.cancel()
        if not action.done():
            action.cancel()
        await asyncio.gather(action, return_exceptions=True)


@pytest.mark.parametrize("boundary", [1, 2, 3])
@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("retry", [False, True])
async def test_discovery_init_failure_retry(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    entity_registry: er.EntityRegistry,
    smarwi_entry: MockConfigEntry,
    cover_id: str,
    dispatcher_spy: Mock,
    monkeypatch: pytest.MonkeyPatch,
    boundary: int,
    cancel: bool,
    retry: bool,
) -> None:
    """Roll back each injected acquisition failure through HA MQTT discovery."""
    active_cache = smarwi_entry.runtime_data
    active_device = active_cache[DEVICE_ID]
    remote_id = "offline_other_remote"
    serial = "offline_other_serial"
    base_topic = f"ion/{remote_id}/%{serial}"
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_REMOTE_ID: remote_id})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    dispatcher_spy.reset_mock()
    subscribe = mqtt.async_subscribe
    cleanups: list[Mock] = []
    attempts = 0
    failed_task: asyncio.Task[object] | None = None

    async def acquire(
        hass: HomeAssistant,
        topic: str,
        msg_callback: Callable[[mqtt.ReceiveMessage], Coroutine[None, None, None]],
        qos: int = 0,
        encoding: str | None = "utf-8",
    ) -> Mock:
        nonlocal attempts, failed_task
        attempts += 1
        if attempts == boundary:
            failed_task = asyncio.current_task()
            if cancel:
                raise asyncio.CancelledError
            raise RuntimeError("Synthetic subscription failure")
        cleanup = Mock(wraps=await subscribe(hass, topic, msg_callback, qos, encoding))
        cleanups.append(cleanup)
        return cleanup

    with monkeypatch.context() as patch:
        patch.setattr(mqtt, "async_subscribe", acquire)
        async_fire_mqtt_message(hass, f"{base_topic}/online", "1")
        await hass.async_block_till_done()
    assert failed_task is not None
    assert failed_task.cancelled() is cancel
    assert attempts == boundary
    # Check stale delivery before cache assertions so leaked listeners are visible.
    dispatcher_spy.reset_mock()
    async_fire_mqtt_message(hass, f"{base_topic}/status", STATUS)
    await hass.async_block_till_done()
    dispatcher_spy.assert_not_called()
    assert not er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert entry.runtime_data == {}
    for cleanup in cleanups:
        cleanup.assert_called_once_with()

    if not retry:
        assert await hass.config_entries.async_unload(entry.entry_id)
        for cleanup in cleanups:
            cleanup.assert_called_once_with()
        assert smarwi_entry.runtime_data is active_cache
        assert active_cache[DEVICE_ID] is active_device
        async_fire_mqtt_message(
            hass, f"{BASE_TOPIC}/status", STATUS.replace("pos:o", "pos:c")
        )
        await hass.async_block_till_done()
        state = hass.states.get(cover_id)
        assert state is not None and state.state == "closed"
        return

    with monkeypatch.context() as patch:
        patch.setattr(mqtt, "async_subscribe", acquire)
        async_fire_mqtt_message(hass, f"{base_topic}/online", "1")
        await hass.async_block_till_done()
    assert attempts == boundary + 3
    assert set(entry.runtime_data) == {serial}
    dispatcher_spy.reset_mock()
    async_fire_mqtt_message(hass, f"{base_topic}/status", STATUS)
    await hass.async_block_till_done()
    assert dispatcher_spy.call_count == 2  # one discovery and one status update
    covers = [
        item
        for item in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        if item.domain == "cover"
    ]
    assert len(covers) == 1
    assert covers[0].unique_id == f"{serial}_cover"
    state = hass.states.get(covers[0].entity_id)
    assert state is not None
    assert state.attributes["device_class"] == CoverDeviceClass.WINDOW
    assert state.attributes["supported_features"] == (
        CoverEntityFeature.OPEN_TILT
        | CoverEntityFeature.CLOSE_TILT
        | CoverEntityFeature.STOP_TILT
        | CoverEntityFeature.SET_TILT_POSITION
    )
    assert await hass.config_entries.async_unload(entry.entry_id)
    for cleanup in cleanups:
        cleanup.assert_called_once_with()
    dispatcher_spy.reset_mock()
    async_fire_mqtt_message(hass, f"{base_topic}/status", STATUS)
    await hass.async_block_till_done()
    dispatcher_spy.assert_not_called()
    assert smarwi_entry.runtime_data is active_cache
    assert active_cache[DEVICE_ID] is active_device
    async_fire_mqtt_message(
        hass, f"{BASE_TOPIC}/status", STATUS.replace("pos:o", "pos:c")
    )
    await hass.async_block_till_done()
    state = hass.states.get(cover_id)
    assert state is not None and state.state == "closed"


@pytest.mark.parametrize(
    "outcome", ["success", "failure", "cancel", "unload", "failed_unload"]
)
async def test_discovery_init_suspended_subscription(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    entity_registry: er.EntityRegistry,
    dispatcher_spy: Mock,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    """An explicit test-only yield probes duplicates, retained status and teardown."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_REMOTE_ID: REMOTE_ID})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    subscribe = mqtt.async_subscribe
    entered = asyncio.Event()
    release = asyncio.Event()
    status_received = asyncio.Event()
    cleanups: list[Mock] = []
    attempts = 0
    init_task: asyncio.Task[object] | None = None

    async def acquire(
        hass: HomeAssistant,
        topic: str,
        msg_callback: Callable[[mqtt.ReceiveMessage], Coroutine[None, None, None]],
        qos: int = 0,
        encoding: str | None = "utf-8",
    ) -> Mock:
        nonlocal attempts, init_task
        attempts += 1
        if attempts == 2:
            init_task = asyncio.current_task()
            entered.set()
            await release.wait()
            if outcome == "failure":
                raise RuntimeError("Synthetic suspended subscription failure")
        if attempts == 1:
            original_handler = msg_callback

            async def status_handler(msg: mqtt.ReceiveMessage) -> None:
                status_received.set()
                await original_handler(msg)

            msg_callback = status_handler
        cleanup = Mock(wraps=await subscribe(hass, topic, msg_callback, qos, encoding))
        cleanups.append(cleanup)
        return cleanup

    with monkeypatch.context() as patch:
        patch.setattr(mqtt, "async_subscribe", acquire)
        async_fire_mqtt_message(hass, f"{BASE_TOPIC}/online", "1")
        try:
            await asyncio.wait_for(entered.wait(), 1)
            cache = entry.runtime_data
            device = cache[DEVICE_ID]
            async_fire_mqtt_message(hass, f"{BASE_TOPIC}/online", "1")
            async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", STATUS, retain=True)
            await asyncio.wait_for(status_received.wait(), 1)
            provisional_dispatches = dispatcher_spy.call_count
            assert attempts == 2
            assert cache[DEVICE_ID] is device
            if outcome == "unload":
                assert await hass.config_entries.async_unload(entry.entry_id)
            if outcome == "failed_unload":
                with monkeypatch.context() as unload_patch:
                    unload_patch.setattr(
                        hass.config_entries,
                        "async_unload_platforms",
                        AsyncMock(return_value=False),
                    )
                    assert not await hass.config_entries.async_unload(entry.entry_id)
                assert entry.runtime_data is cache
                for cleanup in cleanups:
                    cleanup.assert_not_called()
            assert init_task is not None
            if outcome == "cancel":
                init_task.cancel()
        finally:
            release.set()
        await hass.async_block_till_done()
    assert init_task.cancelled() is (outcome in {"cancel", "unload"})
    # No platform may attach an entity to a provisional device.
    assert provisional_dispatches == 0
    if outcome in {"success", "failed_unload"}:
        covers = [
            item
            for item in er.async_entries_for_config_entry(
                entity_registry, entry.entry_id
            )
            if item.domain == "cover"
        ]
        assert len(covers) == 1
        assert device._status
    else:
        assert cache == {}
        assert not er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    if outcome == "failed_unload":
        for cleanup in cleanups:
            cleanup.assert_not_called()
        return
    if outcome != "unload":
        assert await hass.config_entries.async_unload(entry.entry_id)
    for cleanup in cleanups:
        cleanup.assert_called_once_with()
    dispatcher_spy.reset_mock()
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/status", STATUS)
    await hass.async_block_till_done()
    dispatcher_spy.assert_not_called()
