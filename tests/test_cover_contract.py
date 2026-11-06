"""Direct tilt-entity contract tests, not HA setup or service-registry tests."""

from types import SimpleNamespace
from typing import cast
import unittest
from unittest.mock import AsyncMock, patch

from homeassistant.components import mqtt
from homeassistant.components.cover import (
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)

from custom_components.smarwi.cover import SmarwiCover
from custom_components.smarwi.device import SmarwiDevice, StateCode


class CoverContractTests(unittest.IsolatedAsyncioTestCase):
    """Exercise the real entity with a fake device and no Home Assistant instance."""

    def setUp(self) -> None:
        """Prepare only mock commands and prevent accidental transport calls."""
        self.device = SimpleNamespace(
            id="offline_fixture",
            basic_device_info={},
            ridge_fixed=True,
            closed=True,
            state_code=StateCode.IDLE,
            async_open=AsyncMock(),
            async_close=AsyncMock(),
            async_stop=AsyncMock(),
        )
        blocked_io = AssertionError("Contract tests must not use network or MQTT")
        patches = (
            patch("socket.socket.connect", side_effect=blocked_io),
            patch("socket.socket.connect_ex", side_effect=blocked_io),
            patch("socket.socket.sendto", side_effect=blocked_io),
            patch("socket.create_connection", side_effect=blocked_io),
            patch("socket.getaddrinfo", side_effect=blocked_io),
            patch.object(mqtt, "async_publish", side_effect=blocked_io),
            patch.object(mqtt, "async_subscribe", side_effect=blocked_io),
        )
        for guard in patches:
            guard.start()
            self.addCleanup(guard.stop)
        self.cover = SmarwiCover(cast(SmarwiDevice, self.device))

    def test_exact_window_tilt_features(self) -> None:
        """Expose WINDOW and exactly the four tilt features, not standard controls."""
        expected = (
            CoverEntityFeature.OPEN_TILT
            | CoverEntityFeature.CLOSE_TILT
            | CoverEntityFeature.SET_TILT_POSITION
            | CoverEntityFeature.STOP_TILT
        )
        self.assertEqual(self.cover.device_class, CoverDeviceClass.WINDOW)
        self.assertEqual(self.cover.supported_features, expected)
        standard = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.SET_POSITION
            | CoverEntityFeature.STOP
        )
        self.assertFalse(self.cover.supported_features & standard)

    def test_no_standard_action_aliases(self) -> None:
        """Keep standard methods inherited rather than aliasing them to tilt actions."""
        for name in (
            "open_cover",
            "close_cover",
            "set_cover_position",
            "stop_cover",
            "async_open_cover",
            "async_close_cover",
            "async_set_cover_position",
            "async_stop_cover",
        ):
            with self.subTest(method=name):
                self.assertIs(getattr(SmarwiCover, name), getattr(CoverEntity, name))

    def test_tilt_position_does_not_become_standard_position(self) -> None:
        """Report values through the tilt property, leaving unknown tilt as None."""
        self.assertIsNone(self.cover.current_cover_tilt_position)
        self.assertIsNone(self.cover.current_cover_position)
        for position in (0, 10, 100):
            with self.subTest(position=position):
                self.cover._position = position
                self.assertEqual(self.cover.current_cover_tilt_position, position)
                self.assertIsNone(self.cover.current_cover_position)

    def test_closed_state_tracks_the_device(self) -> None:
        """Tilt-only features retain the cover's observed closed-state property."""
        self.assertTrue(self.cover.is_closed)
        self.device.closed = False
        self.assertFalse(self.cover.is_closed)

    async def test_open_tilt_delegates_once(self) -> None:
        """The native open-tilt method delegates to the device open command."""
        await self.cover.async_open_cover_tilt()
        self.device.async_open.assert_awaited_once_with()
        self.device.async_close.assert_not_awaited()
        self.device.async_stop.assert_not_awaited()

    async def test_close_tilt_delegates_once(self) -> None:
        """The native close-tilt method delegates to the device close command."""
        await self.cover.async_close_cover_tilt()
        self.device.async_close.assert_awaited_once_with()
        self.device.async_open.assert_not_awaited()
        self.device.async_stop.assert_not_awaited()

    async def test_set_tilt_uses_tilt_position_payload(self) -> None:
        """Pass 0, 1, intermediate and 100 through the entity's tilt API unchanged."""
        for position in (0, 1, 10, 30, 100):
            with self.subTest(position=position):
                self.device.async_open.reset_mock()
                await self.cover.async_set_cover_tilt_position(
                    **{ATTR_TILT_POSITION: position}
                )
                self.device.async_open.assert_awaited_once_with(position)
        # This does not exercise the known device.async_open(1) wire-payload defect.
        self.device.async_close.assert_not_awaited()
        self.device.async_stop.assert_not_awaited()

    async def test_stop_tilt_while_moving_clears_inferred_position(self) -> None:
        """Exercise Stop in a moving state, not its idle early-return path."""
        self.device.closed = False
        self.device.state_code = StateCode.OPENING
        self.cover._position = 10
        self.cover._requested_position = 30
        await self.cover.async_stop_cover_tilt()
        self.device.async_stop.assert_awaited_once_with()
        self.device.async_open.assert_not_awaited()
        self.device.async_close.assert_not_awaited()
        self.assertIsNone(self.cover.current_cover_tilt_position)
        self.assertEqual(self.cover._requested_position, -1)


if __name__ == "__main__":
    unittest.main()
