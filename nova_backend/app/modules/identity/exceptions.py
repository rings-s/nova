from app.core.exceptions import ConflictError, NotFoundError, ValidationDomainError
from app.core.security import AuthenticationError, AuthorizationError


class TenantNotFoundError(NotFoundError):
    code = "tenant_not_found"

    def __init__(self, tenant_id: object) -> None:
        super().__init__(f"Tenant '{tenant_id}' was not found.")


class DuplicateSlugError(ConflictError):
    code = "duplicate_slug"

    def __init__(self, slug: str) -> None:
        super().__init__(f"Slug '{slug}' is already in use.")


class CustomerNotFoundError(NotFoundError):
    code = "customer_not_found"

    def __init__(self, customer_id: object) -> None:
        super().__init__(f"Customer '{customer_id}' was not found.")


class DuplicatePhoneError(ConflictError):
    code = "duplicate_customer_phone"

    def __init__(self, phone: str) -> None:
        super().__init__(f"A customer with phone '{phone}' already exists for this business.")


class CustomerPhoneRequiredError(ValidationDomainError):
    """A self-booking account with no phone number cannot become a customer.

    The ticket and the WhatsApp confirmation both need a reachable number, and
    inventing a placeholder would put an unroutable record in the salon's book.
    """

    code = "customer_phone_required"

    def __init__(self) -> None:
        super().__init__(
            "Add a phone number to your account before booking, so the salon can reach you."
        )


class PhoneVerificationRequiredError(ValidationDomainError):
    """This account's phone matches an existing, unclaimed customer record —
    but the number has not been proven yet (docs/14 TM-01).

    Before this existed, a self-service booking claimed that record on the
    strength of a phone number nobody had verified, which read (and, on any
    committing path, permanently took over) whoever the salon already knew by
    that number. `AuthService.request_phone_verification` /
    `confirm_phone_verification` are the way past this.
    """

    code = "phone_verification_required"

    def __init__(self) -> None:
        super().__init__(
            "Verify your phone number (POST /auth/phone/verify/request, then "
            "/confirm) before this can be linked to your account."
        )


class MembershipNotFoundError(NotFoundError):
    code = "membership_not_found"

    def __init__(self, membership_id: object) -> None:
        super().__init__(f"Membership '{membership_id}' was not found.")


class DuplicateMembershipError(ConflictError):
    """The person already works here.

    Distinguished from a role change on purpose: silently rewriting an active
    member's role from the grant endpoint would let a mistyped role downgrade
    somebody without the caller noticing.
    """

    code = "duplicate_membership"

    def __init__(self, email: str) -> None:
        super().__init__(
            f"'{email}' already has access to this business. "
            "Change their role instead of granting it again."
        )


class InvalidInviteError(AuthenticationError):
    """The token presented to accept an invite proves nothing.

    One answer for "no such invite", "wrong token", "already accepted" and
    "expired" — same reasoning as `InvalidCredentialsError`: distinguishing
    them would let a caller probe which invite ids exist and are still live.
    """

    code = "invalid_invite"

    def __init__(self) -> None:
        super().__init__("This invite is invalid, expired, or already used.")


class LastOwnerError(ConflictError):
    """A business must keep at least one owner, or nobody can administer it.

    There is no platform-support back door to undo this, which is exactly why
    the rule is enforced here rather than left to the caller's judgement.
    """

    code = "last_owner"

    def __init__(self) -> None:
        super().__init__("This is the only owner of the business. Appoint another owner first.")


class InsufficientRoleError(AuthorizationError):
    """The caller is staff, but their role in this business does not reach this.

    Its own code rather than `forbidden`, so a client can say "ask an owner"
    instead of "you are not allowed in".
    """

    code = "insufficient_role"

    def __init__(self, permission: object) -> None:
        super().__init__(f"Your role in this business does not allow '{permission}'.")
