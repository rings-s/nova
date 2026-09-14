"""discovery · DOMAIN layer — module errors."""

from app.core.exceptions import NotFoundError


class ListingNotFoundError(NotFoundError):
    """No published storefront at this slug.

    Deliberately one error for three different situations: the slug does not
    exist, the business exists but is switched off, and the business exists but
    has been de-listed (an unpaid invoice at day 21, docs/11 section 8).

    Distinguishing them would turn the public storefront into an oracle for
    which salons are on NOVA and which are behind on their bill — information a
    competitor would find useful and a customer never would.
    """

    code = "listing_not_found"

    def __init__(self, slug: str) -> None:
        super().__init__(f"No published listing for '{slug}'.")
