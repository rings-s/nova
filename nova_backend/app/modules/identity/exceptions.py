from app.core.exceptions import ConflictError, NotFoundError, ValidationDomainError


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


class UserNotFoundError(NotFoundError):
    """No account exists for the address an owner tried to add.

    NOVA has no invite flow yet — `POST /memberships` grants access to an
    account that already exists, so an unknown address is a 404 rather than a
    pending invitation. That does make the endpoint answer "is this address
    registered?", but only for a caller who has already proven they administer
    a salon, and only at the write rate limit.
    """

    code = "user_not_found"

    def __init__(self, email: str) -> None:
        super().__init__(f"No NOVA account is registered for '{email}'.")


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


class LastOwnerError(ConflictError):
    """A business must keep at least one owner, or nobody can administer it.

    There is no platform-support back door to undo this, which is exactly why
    the rule is enforced here rather than left to the caller's judgement.
    """

    code = "last_owner"

    def __init__(self) -> None:
        super().__init__("This is the only owner of the business. Appoint another owner first.")
