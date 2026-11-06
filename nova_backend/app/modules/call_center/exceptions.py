"""call_center · DOMAIN layer — module errors."""

from app.core.exceptions import ConflictError, NotFoundError


class PhoneLineNotFoundError(NotFoundError):
    code = "phone_line_not_found"

    def __init__(self, line_id: object) -> None:
        super().__init__(f"Phone line '{line_id}' was not found.")


class PhoneNumberTakenError(ConflictError):
    """A number rings one business. Two lines on it would route a call by chance."""

    code = "phone_number_taken"

    def __init__(self, number: str) -> None:
        super().__init__(f"The number {number} is already a NOVA phone line.")


class CallNotFoundError(NotFoundError):
    """Also the answer to a forged or expired call link: 404, never "forbidden"."""

    code = "call_not_found"

    def __init__(self) -> None:
        super().__init__("This call was not found.")


class AudioNotFoundError(NotFoundError):
    """A clip of Sara's voice that is unknown or has expired."""

    code = "audio_not_found"

    def __init__(self) -> None:
        super().__init__("This audio was not found or has expired.")


class CallEndedError(ConflictError):
    code = "call_ended"

    def __init__(self) -> None:
        super().__init__("This call has already ended.")
