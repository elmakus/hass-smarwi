"""Key/value syntax regressions for the shared MQTT payload decoder."""

import pytest

from custom_components.smarwi.device import decode_keyval


@pytest.mark.parametrize(
    "payload",
    [
        "cid:Window: fixture\nfw:\nfuture:kept",
        "cid:Window: fixture\nfw:\nfuture:kept\n",
        "\ncid:Window: fixture\n\nfw:\nfuture:kept\n\n",
        "\r\ncid:Window: fixture\r\n\r\nfw:\r\nfuture:kept\r\n\r\n",
    ],
)
def test_decode_keyval_preserves_values_and_ignores_empty_lines(payload: str) -> None:
    """Preserve unknown keys, empty values and colons within values."""
    assert decode_keyval(payload) == {
        "cid": "Window: fixture",
        "fw": "",
        "future": "kept",
    }


@pytest.mark.parametrize("payload", ["", "\n", "\n\n", "\r\n\r\n"])
def test_decode_keyval_empty_message_has_no_records(payload: str) -> None:
    """Leave the decision to ignore an empty snapshot to the callers."""
    assert decode_keyval(payload) == {}


@pytest.mark.parametrize(
    "payload", ["broken", "s:250\nbroken", "broken\ns:250", "s:250\n \ns:210"]
)
def test_decode_keyval_rejects_a_nonempty_line_without_a_colon(payload: str) -> None:
    """Never return only the valid part of a malformed message."""
    with pytest.raises(ValueError):
        decode_keyval(payload)
