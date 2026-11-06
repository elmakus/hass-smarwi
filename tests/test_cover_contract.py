"""Direct tilt-entity contract tests, not HA setup or service-registry tests."""

import asyncio
from collections.abc import Coroutine
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
from custom_components.smarwi.device import SmarwiDevice, SmarwiDeviceProp, StateCode


class CoverContractTests(unittest.IsolatedAsyncioTestCase):
    """Exercise the real entity with a fake device and no Home Assistant instance."""

    def setUp(self) -> None:
        """Prepare only mock commands and prevent accidental transport calls."""
        self.device = SimpleNamespace(
            id="offline_fixture",
            basic_device_info={},
            ridge_fixed=True,
            closed=False,
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
        """Report only binary closed zero, never private estimates as feedback."""
        for closed in (True, False, None):
            self.device.closed = closed
            for position in (-1, 0, 5, 30, 100):
                with self.subTest(closed=closed, position=position):
                    self.cover._position = position
                    self.assertEqual(
                        self.cover.current_cover_tilt_position,
                        0 if closed is True else None,
                    )
                    self.assertIsNone(self.cover.current_cover_position)

    def test_closed_state_tracks_the_device(self) -> None:
        """Tilt-only features retain the cover's observed closed-state property."""
        self.assertFalse(self.cover.is_closed)
        self.device.closed = True
        self.assertTrue(self.cover.is_closed)
        self.assertEqual(self.cover.current_cover_tilt_position, 0)

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
        self.assertEqual(self.cover._position, 10)
        self.assertEqual(self.cover._requested_position, 30)
        self.assertIsNone(self.cover.current_cover_tilt_position)
        await self.cover.async_stop_cover_tilt()
        self.device.async_stop.assert_awaited_once_with()
        self.device.async_open.assert_not_awaited()
        self.device.async_close.assert_not_awaited()
        self.assertIsNone(self.cover.current_cover_tilt_position)
        self.assertEqual(self.cover._requested_position, -1)
        self.assertEqual(self.cover._position, -1)

    async def _pending_request(
        self, action: Coroutine[None, None, None], command: AsyncMock
    ) -> tuple[asyncio.Task[None], asyncio.Future[None]]:
        started = asyncio.Event()
        result: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        async def pending(*args: object) -> None:
            started.set()
            await result

        command.side_effect = pending
        task = asyncio.create_task(action)

        async def cleanup() -> None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        self.addAsyncCleanup(cleanup)
        await asyncio.wait_for(started.wait(), 5)
        self.assertFalse(task.done())
        return task, result

    async def test_current_request_failure_clears_only_local_intent(self) -> None:
        """All three actions discard failed intent, not telemetry or motion."""
        for method, command, kwargs, target in (
            (self.cover.async_open_cover_tilt, self.device.async_open, {}, 100),
            (self.cover.async_close_cover_tilt, self.device.async_close, {}, 0),
            (
                self.cover.async_set_cover_tilt_position,
                self.device.async_open,
                {ATTR_TILT_POSITION: 30},
                30,
            ),
        ):
            for cancelled in (False, True):
                with self.subTest(target=target, cancelled=cancelled):
                    self.device.state_code = StateCode.OPENING
                    self.cover._is_moving = True
                    self.cover._position = 10
                    task, result = await self._pending_request(
                        method(**kwargs), command
                    )
                    self.assertEqual(self.cover._requested_position, target)
                    error = RuntimeError("ACK failed after possible delivery")
                    if cancelled:
                        task.cancel("explicit cancellation")
                        with self.assertRaises(asyncio.CancelledError) as caught:
                            await task
                        self.assertEqual(
                            caught.exception.args, ("explicit cancellation",)
                        )
                    else:
                        result.set_exception(error)
                        with self.assertRaises(RuntimeError) as caught:
                            await task
                        self.assertIs(caught.exception, error)
                    self.assertEqual(self.cover._requested_position, -1)
                    self.assertEqual(self.cover._position, -1)
                    self.assertIsNone(self.cover._intent_owner)
                    self.assertTrue(self.cover._is_moving)
                    self.assertIs(self.device.state_code, StateCode.OPENING)
                    self.assertIs(self.device.closed, False)

    async def test_same_target_supersession_uses_request_identity(self) -> None:
        """Old failures/cancellation cannot clear a newer numerically equal request."""
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                self.cover._position = 10
                first, first_result = await self._pending_request(
                    self.cover.async_open_cover_tilt(), self.device.async_open
                )
                first_owner = self.cover._intent_owner
                second, second_result = await self._pending_request(
                    self.cover.async_open_cover_tilt(), self.device.async_open
                )
                second_owner = self.cover._intent_owner
                if cancelled:
                    first.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await first
                else:
                    error = RuntimeError("old failure")
                    first_result.set_exception(error)
                    with self.assertRaises(RuntimeError) as caught:
                        await first
                    self.assertIs(caught.exception, error)
                self.assertEqual(self.cover._requested_position, 100)
                self.assertEqual(self.cover._position, 10)
                self.assertIs(self.cover._intent_owner, second_owner)
                second_error = RuntimeError("new failure")
                second_result.set_exception(second_error)
                with self.assertRaises(RuntimeError) as caught:
                    await second
                self.assertIs(caught.exception, second_error)
                self.assertEqual(self.cover._requested_position, -1)
                self.assertIsNotNone(first_owner)
                self.assertIsNotNone(second_owner)
                self.assertIsNot(first_owner, second_owner)
                self.assertEqual(self.cover._position, -1)
                self.assertIsNone(self.cover._intent_owner)

    async def test_late_success_after_new_failure_never_restores_intent(self) -> None:
        """A late successful ACK cannot resurrect A after B failed."""
        first, result = await self._pending_request(
            self.cover.async_open_cover_tilt(), self.device.async_open
        )
        error = RuntimeError("new failure")
        self.device.async_close.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            await self.cover.async_close_cover_tilt()
        self.assertIs(caught.exception, error)
        result.set_result(None)
        await first
        self.assertEqual(self.cover._requested_position, -1)
        self.assertEqual(self.cover._position, -1)
        self.assertIsNone(self.cover._intent_owner)

    async def test_existing_invalidation_disowns_pending_request(self) -> None:
        """Stop/error/actual idle cleanup disown ACKs, preserving terminal estimates."""
        self.device.name = "Offline fixture"
        with patch.object(self.cover, "async_write_ha_state"):
            for invalidation in ("stop", "error", "closed_idle", "open_idle"):
                for outcome in ("success", "failure", "cancel"):
                    with self.subTest(invalidation=invalidation, outcome=outcome):
                        self.device.closed = False
                        self.device.state_code = StateCode.OPENING
                        self.cover._is_moving = True
                        self.cover._position = 10
                        task, result = await self._pending_request(
                            self.cover.async_open_cover_tilt(), self.device.async_open
                        )
                        self.assertIsNotNone(self.cover._intent_owner)
                        if invalidation == "stop":
                            await self.cover.async_stop_cover_tilt()
                            expected = -1
                        else:
                            self.device.closed = invalidation == "closed_idle"
                            self.device.state_code = (
                                StateCode.ERR_MOVE_TIMEOUT
                                if invalidation == "error"
                                else StateCode.IDLE
                            )
                            await self.cover.async_handle_update(
                                {SmarwiDeviceProp.STATE_CODE, SmarwiDeviceProp.CLOSED}
                            )
                            expected = {
                                "error": -1,
                                "closed_idle": 0,
                                "open_idle": 100,
                            }[invalidation]
                        self.assertEqual(self.cover._position, expected)
                        self.assertEqual(self.cover._requested_position, -1)
                        self.assertIsNone(self.cover._intent_owner)
                        if outcome == "success":
                            result.set_result(None)
                            await task
                        elif outcome == "cancel":
                            task.cancel()
                            with self.assertRaises(asyncio.CancelledError):
                                await task
                        else:
                            error = RuntimeError("late failure")
                            result.set_exception(error)
                            with self.assertRaises(RuntimeError) as caught:
                                await task
                            self.assertIs(caught.exception, error)
                        self.assertEqual(self.cover._position, expected)
                        self.assertEqual(self.cover._requested_position, -1)
                        self.assertIsNone(self.cover._intent_owner)

    async def test_noninvalidating_updates_and_idle_stop_preserve_owner(self) -> None:
        """Keep inherited idle/release/availability limitations explicit."""
        self.device.name = "Offline fixture"
        task, result = await self._pending_request(
            self.cover.async_open_cover_tilt(), self.device.async_open
        )
        owner = self.cover._intent_owner
        self.assertIsNotNone(owner)
        with patch.object(self.cover, "async_write_ha_state"):
            await self.cover.async_stop_cover_tilt()
            for props in (
                set(),
                {SmarwiDeviceProp.AVAILABLE},
                {SmarwiDeviceProp.RIDGE_FIXED},
            ):
                await self.cover.async_handle_update(props)
                self.assertIs(self.cover._intent_owner, owner)
                self.assertEqual(self.cover._requested_position, 100)
        self.device.async_stop.assert_not_awaited()
        result.set_result(None)
        await task
        self.assertIs(self.cover._intent_owner, owner)
        self.assertEqual(self.cover._requested_position, 100)


if __name__ == "__main__":
    unittest.main()
