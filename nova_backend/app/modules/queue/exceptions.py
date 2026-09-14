"""queue · DOMAIN layer — module errors.

The lifecycle and ticket-validity errors live in `domain.py` beside the state
machines they guard (`InvalidQueueTransition`, `QueueClosedError`,
`TicketInvalidError`); this file holds the rest.
"""

from app.core.exceptions import ConflictError, NotFoundError


class QueueNotFoundError(NotFoundError):
    code = "queue_not_found"

    def __init__(self, queue_id: object) -> None:
        super().__init__(f"Queue '{queue_id}' was not found.")


class QueueEntryNotFoundError(NotFoundError):
    code = "queue_entry_not_found"

    def __init__(self, entry_id: object) -> None:
        super().__init__(f"Queue entry '{entry_id}' was not found.")


class AlreadyInQueueError(ConflictError):
    """One person, one place in the line.

    Without this a customer can rejoin repeatedly and appear several times in
    the same queue, which quietly breaks both the ordering and the wait
    estimate for everyone behind them.
    """

    code = "already_in_queue"

    def __init__(self) -> None:
        super().__init__("This customer is already waiting in that queue.")


class NoOneWaitingError(ConflictError):
    code = "no_one_waiting"

    def __init__(self) -> None:
        super().__init__("There is nobody waiting in this queue.")
