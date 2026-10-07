"""The turn limiter: a few at once overall, one at a time per caller. No model."""

import asyncio

import pytest

from app.modules.ai_agents.concurrency import InferenceGate
from app.modules.ai_agents.exceptions import AiBusyError


async def test_a_caller_with_a_turn_running_is_refused_a_second() -> None:
    gate = InferenceGate(max_concurrent=2, queue_wait_seconds=0.05)
    async with gate.slot("alice"):
        with pytest.raises(AiBusyError):
            async with gate.slot("alice"):
                pass  # pragma: no cover


async def test_a_further_turn_waits_for_a_slot_then_is_told_to_retry() -> None:
    gate = InferenceGate(max_concurrent=1, queue_wait_seconds=0.05)
    async with gate.slot("alice"):
        with pytest.raises(AiBusyError):
            async with gate.slot("bob"):
                pass  # pragma: no cover


async def test_a_waiting_turn_gets_the_slot_when_it_frees() -> None:
    gate = InferenceGate(max_concurrent=1, queue_wait_seconds=1.0)
    order: list[str] = []

    async def turn(caller: str, hold: float) -> None:
        async with gate.slot(caller):
            order.append(caller)
            await asyncio.sleep(hold)

    await asyncio.gather(turn("alice", 0.05), turn("bob", 0))

    assert order == ["alice", "bob"]


async def test_a_refused_or_finished_turn_frees_the_caller_and_the_slot() -> None:
    gate = InferenceGate(max_concurrent=1, queue_wait_seconds=0.05)
    async with gate.slot("alice"):
        with pytest.raises(AiBusyError):
            async with gate.slot("bob"):
                pass  # pragma: no cover

    # Bob was refused, Alice finished: both may go again.
    async with gate.slot("bob"):
        pass
    async with gate.slot("alice"):
        pass


async def test_an_error_inside_a_turn_still_releases_everything() -> None:
    gate = InferenceGate(max_concurrent=1, queue_wait_seconds=0.05)
    with pytest.raises(RuntimeError):
        async with gate.slot("alice"):
            raise RuntimeError("model blew up")

    async with gate.slot("alice"):
        pass
