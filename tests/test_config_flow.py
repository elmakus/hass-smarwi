"""Public config-flow tests with no controller, broker, sockets, or DNS."""

import asyncio
import json
from pathlib import Path
import socket
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.config_entries import ConfigFlowResult, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.smarwi.const import CONF_REMOTE_ID, DOMAIN, NAME

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.fixture(autouse=True)
def offline_flow(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Block transport and replace entry setup before a flow can complete."""

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("Config-flow tests must not use sockets or DNS")

    for name in ("connect", "connect_ex", "sendto", "bind", "listen"):
        monkeypatch.setattr(socket.socket, name, fail)
    for name in (
        "create_connection",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "gethostbyaddr",
    ):
        monkeypatch.setattr(socket, name, fail)
    setup = AsyncMock(return_value=True)
    monkeypatch.setattr("homeassistant.config_entries.ConfigEntry.async_setup", setup)
    return setup


async def start_flow(hass: HomeAssistant) -> ConfigFlowResult:
    """Start through HA's public flow manager, not a direct step call."""
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


@pytest.mark.parametrize(
    "remote_id",
    [
        "offline_remote",
        "MiXeD-42:%",
        "room name",
        "remote_🌍",
        "x" * (65535 - len("ion//+/online")),
    ],
)
async def test_valid_literal_id(
    hass: HomeAssistant, offline_flow: AsyncMock, remote_id: str
) -> None:
    """Preserve the literal ID and assign it as the new entry's unique ID."""
    form = await start_flow(hass)
    assert form["type"] is FlowResultType.FORM
    assert not form["errors"]
    assert form["data_schema"]({CONF_REMOTE_ID: remote_id}) == {
        CONF_REMOTE_ID: remote_id
    }
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], {CONF_REMOTE_ID: remote_id}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {CONF_REMOTE_ID: remote_id}
    assert result["result"].unique_id == remote_id
    offline_flow.assert_awaited_once()


@pytest.mark.parametrize(
    "remote_id",
    [
        "",
        " ",
        "\t",
        " outer",
        "outer ",
        "\u00a0outer",
        "a/b",
        "/",
        "+",
        "#",
        "a+b",
        "a#b",
        "a\0b",
        "a\nb",
        "a\tb",
        "a\x7fb",
        "a\x85b",
        "\ud800",
        "\ufdd0",
        "\U0001ffff",
        "x" * (65536 - len("ion//+/online")),
        "é" * 32762,
    ],
)
async def test_invalid_id_then_recover(
    hass: HomeAssistant, offline_flow: AsyncMock, remote_id: object
) -> None:
    """Reject invalid IDs at the field without creating entries; allow correction."""
    form = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], {CONF_REMOTE_ID: remote_id}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_REMOTE_ID: "invalid_remote_id"}
    assert not hass.config_entries.async_entries(DOMAIN)
    offline_flow.assert_not_awaited()
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], {CONF_REMOTE_ID: "corrected"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "corrected"


@pytest.mark.parametrize(
    "data",
    [
        {},
        {CONF_REMOTE_ID: None},
        {CONF_REMOTE_ID: 123},
        {CONF_REMOTE_ID: True},
        {CONF_REMOTE_ID: []},
        {CONF_REMOTE_ID: {}},
    ],
)
async def test_invalid_schema_then_recover(
    hass: HomeAssistant, offline_flow: AsyncMock, data: dict
) -> None:
    """Native HA schema rejection leaves the public flow available for correction."""
    form = await start_flow(hass)
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(form["flow_id"], data)
    assert not hass.config_entries.async_entries(DOMAIN)
    offline_flow.assert_not_awaited()
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], {CONF_REMOTE_ID: "corrected"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "corrected"
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    "unique_id,data_id",
    [
        (None, "existing"),
        ("existing", "existing"),
        ("existing", "legacy_data"),
        ("legacy_unique", "existing"),
    ],
)
async def test_existing_entry_unchanged(
    hass: HomeAssistant, offline_flow: AsyncMock, unique_id: str | None, data_id: str
) -> None:
    """Reject either identity match, including legacy data without a unique ID."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=unique_id, data={CONF_REMOTE_ID: data_id}
    )
    entry.add_to_hass(hass)
    form = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], {CONF_REMOTE_ID: "existing"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert hass.config_entries.async_entries(DOMAIN) == [entry]
    assert entry.unique_id == unique_id
    assert entry.data == {CONF_REMOTE_ID: data_id}
    offline_flow.assert_not_awaited()


async def test_literal_identity_is_case_sensitive(hass: HomeAssistant) -> None:
    """Do not merge different literal topic segments."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_REMOTE_ID: "Existing"})
    entry.add_to_hass(hass)
    form = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], {CONF_REMOTE_ID: "existing"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "existing"
    await hass.async_block_till_done()
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


async def test_concurrent_duplicate_flows(
    hass: HomeAssistant, offline_flow: AsyncMock
) -> None:
    """Two user forms submitted together must create exactly one entry."""
    first, second = await asyncio.gather(start_flow(hass), start_flow(hass))
    results = await asyncio.gather(
        *(
            hass.config_entries.flow.async_configure(
                form["flow_id"], {CONF_REMOTE_ID: "same"}
            )
            for form in (first, second)
        )
    )
    await hass.async_block_till_done()
    assert sorted(result["type"].value for result in results) == [
        "abort",
        "create_entry",
    ]
    assert next(result for result in results if result["type"] is FlowResultType.ABORT)[
        "reason"
    ] in {"already_configured", "already_in_progress"}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert hass.config_entries.async_entries(DOMAIN)[0].unique_id == "same"
    offline_flow.assert_awaited_once()


async def test_native_in_progress_guard(
    hass: HomeAssistant, offline_flow: AsyncMock
) -> None:
    """Honor a unique ID already reserved by another native HA flow."""
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER, "unique_id": "reserved"}
    )
    second = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        second["flow_id"], {CONF_REMOTE_ID: "reserved"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_in_progress"
    assert result["translation_domain"] == "homeassistant"
    assert not hass.config_entries.async_entries(DOMAIN)
    offline_flow.assert_not_awaited()
    hass.config_entries.flow.async_abort(first["flow_id"])


def test_english_flow_messages() -> None:
    """Ship English text for integration-owned field errors and aborts."""
    translations = json.loads(
        (
            Path(__file__).parents[1] / "custom_components/smarwi/translations/en.json"
        ).read_text()
    )
    assert translations["config"]["error"]["invalid_remote_id"]
    assert translations["config"]["abort"]["already_configured"]
