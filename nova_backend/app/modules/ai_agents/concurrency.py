"""ai_agents · how many turns may run at once.

A turn holds a model-server slot for seconds to minutes. A local server loaded
with `--parallel 1` serves one at a time, so without a limit one customer
sending turns back to back, or a handful of tenants at once, queues everyone
behind them while each waiting turn also holds an API worker. The gate bounds
both: a few turns in flight overall, and one per caller.

It is per process. With several API replicas the model server is the shared
resource, so set the limit to its slot count divided by the replicas.
"""

import asyncio
import weakref
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.modules.ai_agents.exceptions import AiBusyError


class InferenceGate:
    def __init__(self, *, max_concurrent: int, queue_wait_seconds: float) -> None:
        self.max_concurrent = max_concurrent
        self.queue_wait_seconds = queue_wait_seconds
        self._slots = asyncio.Semaphore(max_concurrent)
        self._callers: set[str] = set()

    @asynccontextmanager
    async def slot(self, caller: str) -> AsyncIterator[None]:
        """Holds one slot for the caller's turn, or raises `AiBusyError`."""
        if caller in self._callers:
            # One turn at a time each: a second tab or a retry loop must wait for
            # the answer it already asked for.
            raise AiBusyError("You already have a message being answered. Wait for the reply.")
        self._callers.add(caller)
        try:
            try:
                await asyncio.wait_for(self._slots.acquire(), self.queue_wait_seconds)
            except TimeoutError:
                raise AiBusyError("The assistant is busy. Try again in a moment.") from None
            try:
                yield
            finally:
                self._slots.release()
        finally:
            self._callers.discard(caller)


#: One gate per event loop. A semaphore binds to the loop it first waits on, and
#: tests (and `--reload`) run several loops in one process.
_gates: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, InferenceGate]" = (
    weakref.WeakKeyDictionary()
)


def get_inference_gate(*, max_concurrent: int, queue_wait_seconds: float) -> InferenceGate:
    loop = asyncio.get_running_loop()
    gate = _gates.get(loop)
    if gate is None:
        gate = _gates[loop] = InferenceGate(
            max_concurrent=max_concurrent, queue_wait_seconds=queue_wait_seconds
        )
    return gate
