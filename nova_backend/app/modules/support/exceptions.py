"""support · DOMAIN layer — module errors."""

from uuid import UUID

from app.core.exceptions import NotFoundError


class FollowUpNotFoundError(NotFoundError):
    code = "follow_up_not_found"

    def __init__(self, follow_up_id: UUID) -> None:
        super().__init__(f"Follow-up {follow_up_id} was not found.")
