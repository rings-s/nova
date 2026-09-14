"""Booking attribution — the signal commission is computed from.

Pure: no database, no HTTP. `BookingSource` decides whether NOVA may charge a
salon for a booking (docs/11 sections 3, 4 and 9), and the billing module that
will read it does not exist yet. These tests are what stop the field drifting
back into a UI label before that module arrives.

The rule these exist to protect, from docs/11:

    "A customer is charged as 'new' exactly once, per business, forever. Any
     bug that re-charges an existing customer is a P1."

Every assertion below leans the same way: when attribution is uncertain, the
booking is free.
"""

from uuid import uuid4

import pytest

from app.core.security import AuthorizationError, Principal, PrincipalKind
from app.modules.booking.dependencies import (
    CLIENT_DECLARABLE_SOURCES,
    resolve_booking_source,
)
from app.modules.booking.domain import NEVER_BILLABLE_SOURCES, BookingSource


def customer() -> Principal:
    return Principal(subject_id=uuid4(), kind=PrincipalKind.CUSTOMER)


def staff() -> Principal:
    return Principal(subject_id=uuid4(), kind=PrincipalKind.STAFF)


class TestTheVocabulary:
    """docs/11 section 4 names six sources. All six, and only these six."""

    def test_every_documented_source_exists(self):
        assert {s.value for s in BookingSource} == {
            "marketplace",
            "direct_link",
            "whatsapp",
            "walk_in",
            "reception",
            "ai_agent",
        }

    def test_the_retired_interface_labels_are_gone(self):
        # `pwa` and `staff` described how a booking arrived, not who introduced
        # the customer. `pwa` covered both the marketplace and the salon's own
        # page, which is exactly the distinction commission turns on.
        values = {s.value for s in BookingSource}
        assert "pwa" not in values
        assert "staff" not in values


class TestWhatCanEverBeBilled:
    def test_marketplace_is_the_only_chargeable_source(self):
        billable = set(BookingSource) - NEVER_BILLABLE_SOURCES
        assert billable == {BookingSource.MARKETPLACE}

    @pytest.mark.parametrize(
        "source",
        [
            BookingSource.DIRECT_LINK,
            BookingSource.WHATSAPP,
            BookingSource.WALK_IN,
            BookingSource.RECEPTION,
        ],
    )
    def test_the_free_forever_channels_are_never_billable(self, source):
        """docs/11 section 9: own link, WhatsApp, QR ticket, walk-in queue."""
        assert source in NEVER_BILLABLE_SOURCES

    def test_an_unattributed_agent_booking_is_not_billable(self):
        # docs/11 section 4: an agent "inherits the channel it was reached on".
        # A booking that reached us as a bare `ai_agent` never recorded which
        # channel that was, so it cannot be shown to be a marketplace booking.
        assert BookingSource.AI_AGENT in NEVER_BILLABLE_SOURCES


class TestWhatACallerMayClaim:
    """A request body decides revenue here, so it is only partly trusted."""

    def test_marketplace_cannot_be_claimed_by_a_client(self):
        # The only chargeable source. Letting a caller assert it would let a
        # client invent revenue against a salon that owes none.
        assert BookingSource.MARKETPLACE not in CLIENT_DECLARABLE_SOURCES
        with pytest.raises(AuthorizationError):
            resolve_booking_source(BookingSource.MARKETPLACE, customer(), on_behalf_of=False)

    def test_a_customer_cannot_claim_to_be_reception(self):
        assert BookingSource.RECEPTION not in CLIENT_DECLARABLE_SOURCES
        with pytest.raises(AuthorizationError):
            resolve_booking_source(BookingSource.RECEPTION, customer(), on_behalf_of=False)

    @pytest.mark.parametrize("source", sorted(CLIENT_DECLARABLE_SOURCES))
    def test_a_customer_may_declare_how_they_reached_the_salon(self, source):
        assert resolve_booking_source(source, customer(), on_behalf_of=False) is source

    def test_staff_booking_on_behalf_is_always_reception(self):
        # Whatever the body says. Reception is a counter action; nothing else
        # it could claim is true, and `direct_link` vs `reception` are both
        # free, so this is about an honest audit trail rather than money.
        resolved = resolve_booking_source(BookingSource.WHATSAPP, staff(), on_behalf_of=True)
        assert resolved is BookingSource.RECEPTION

    def test_an_unstated_source_defaults_to_free(self):
        resolved = resolve_booking_source(None, customer(), on_behalf_of=False)
        assert resolved is BookingSource.DIRECT_LINK
        assert resolved in NEVER_BILLABLE_SOURCES

    def test_the_default_never_bills_a_salon_by_accident(self):
        """The direction of the guess matters more than the guess.

        Defaulting to `direct_link` means NOVA under-charges when it cannot
        tell. Defaulting to `marketplace` would charge a salon for a customer
        it already had — the P1 in docs/11 section 3.
        """
        for principal in (customer(), staff()):
            assert (
                resolve_booking_source(None, principal, on_behalf_of=False)
                in NEVER_BILLABLE_SOURCES
            )
