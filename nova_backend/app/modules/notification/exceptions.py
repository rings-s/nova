"""notification · DOMAIN layer — module errors.

The consent and lifecycle errors live in `domain.py` beside the rules they
guard (`ConsentWithheldError`, `InvalidNotificationTransition`).
"""

from app.core.exceptions import NotFoundError


class NotificationNotFoundError(NotFoundError):
    code = "notification_not_found"

    def __init__(self, notification_id: object) -> None:
        super().__init__(f"Notification '{notification_id}' was not found.")
