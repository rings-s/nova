"""Notification rules — consent and quiet hours.

These are the rules that decide whether we are *permitted to speak to someone*,
which makes them the ones worth testing exhaustively: a bug here is either a
PDPL violation or a 2am marketing message.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ConflictError, ValidationDomainError
from app.modules.notification.domain import (
    DELIVERY_BACKOFF_SECONDS,
    MAX_DELIVERY_ATTEMPTS,
    MessageTemplate,
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationStatus,
    category_for,
    has_consent,
    is_within_quiet_hours,
    next_delivery_attempt_at,
    next_send_time,
    render_template_params,
)

RIYADH = "Asia/Riyadh"


def _at(hour: int, minute: int = 0) -> datetime:
    """A UTC instant. Riyadh is UTC+3, so 06:00 UTC is 09:00 local."""
    return datetime(2026, 8, 17, hour, minute, tzinfo=UTC)


class TestTemplateCategories:
    def test_booking_messages_are_transactional(self):
        assert category_for(MessageTemplate.BOOKING_CONFIRMED) is NotificationCategory.TRANSACTIONAL

    def test_win_back_is_marketing(self):
        assert category_for(MessageTemplate.WIN_BACK) is NotificationCategory.MARKETING

    def test_every_template_has_a_category(self):
        # A template with no category would fall through the consent gate.
        for template in MessageTemplate:
            assert category_for(template) in NotificationCategory


class TestConsent:
    def test_whatsapp_needs_whatsapp_consent(self):
        assert not has_consent(
            channel=NotificationChannel.WHATSAPP,
            category=NotificationCategory.TRANSACTIONAL,
            whatsapp_consent=False,
            marketing_consent=True,
        )

    def test_transactional_goes_out_with_channel_consent_alone(self):
        assert has_consent(
            channel=NotificationChannel.WHATSAPP,
            category=NotificationCategory.TRANSACTIONAL,
            whatsapp_consent=True,
            marketing_consent=False,
        )

    def test_marketing_needs_marketing_consent_as_well(self):
        # Agreeing to receive a booking confirmation on WhatsApp is not
        # agreeing to receive offers there.
        assert not has_consent(
            channel=NotificationChannel.WHATSAPP,
            category=NotificationCategory.MARKETING,
            whatsapp_consent=True,
            marketing_consent=False,
        )

    def test_marketing_with_both_consents_is_permitted(self):
        assert has_consent(
            channel=NotificationChannel.WHATSAPP,
            category=NotificationCategory.MARKETING,
            whatsapp_consent=True,
            marketing_consent=True,
        )

    def test_marketing_consent_alone_does_not_unlock_a_channel(self):
        assert not has_consent(
            channel=NotificationChannel.WHATSAPP,
            category=NotificationCategory.MARKETING,
            whatsapp_consent=False,
            marketing_consent=True,
        )


class TestQuietHours:
    def test_late_evening_is_quiet(self):
        # 20:00 UTC is 23:00 in Riyadh.
        assert is_within_quiet_hours(_at(20), timezone=RIYADH, start_hour=22, end_hour=8)

    def test_early_morning_is_quiet(self):
        # 02:00 UTC is 05:00 in Riyadh.
        assert is_within_quiet_hours(_at(2), timezone=RIYADH, start_hour=22, end_hour=8)

    def test_midday_is_not_quiet(self):
        assert not is_within_quiet_hours(_at(9), timezone=RIYADH, start_hour=22, end_hour=8)

    def test_the_window_is_evaluated_in_the_customers_timezone(self):
        # 19:00 UTC is 22:00 in Riyadh — quiet there, still the evening in
        # UTC. Evaluating against the server's clock would send this message
        # at 10pm to a customer in Riyadh.
        instant = _at(19)
        assert is_within_quiet_hours(instant, timezone=RIYADH, start_hour=22, end_hour=8)
        assert not is_within_quiet_hours(instant, timezone="UTC", start_hour=22, end_hour=8)

    def test_boundaries_are_half_open(self):
        # 19:00 UTC = 22:00 Riyadh: quiet starts. 05:00 UTC = 08:00: quiet ends.
        assert is_within_quiet_hours(_at(19), timezone=RIYADH, start_hour=22, end_hour=8)
        assert not is_within_quiet_hours(_at(5), timezone=RIYADH, start_hour=22, end_hour=8)

    def test_an_empty_window_is_never_quiet(self):
        assert not is_within_quiet_hours(_at(3), timezone=RIYADH, start_hour=8, end_hour=8)

    def test_a_non_wrapping_window_works_too(self):
        # 13:00-15:00 local siesta: 11:00 UTC is 14:00 Riyadh.
        assert is_within_quiet_hours(_at(11), timezone=RIYADH, start_hour=13, end_hour=15)
        assert not is_within_quiet_hours(_at(6), timezone=RIYADH, start_hour=13, end_hour=15)


class TestNextSendTime:
    def test_a_held_message_goes_out_when_the_window_opens(self):
        # 22:00 UTC is 01:00 Riyadh; the next 08:00 local is 05:00 UTC.
        released = next_send_time(_at(22), timezone=RIYADH, end_hour=8)
        assert released == datetime(2026, 8, 18, 5, 0, tzinfo=UTC)

    def test_an_evening_message_waits_until_the_next_morning(self):
        # 20:00 UTC is 23:00 Riyadh on the 17th; next opening is the 18th.
        released = next_send_time(_at(20), timezone=RIYADH, end_hour=8)
        assert released == datetime(2026, 8, 18, 5, 0, tzinfo=UTC)

    def test_the_result_is_always_in_the_future(self):
        for hour in range(24):
            assert next_send_time(_at(hour), timezone=RIYADH, end_hour=8) > _at(hour)


class TestDeliveryRetries:
    """A transient BSP failure must not cost the customer their confirmation.

    Before this policy existed, `deliver` set FAILED on the first exception and
    nothing ever re-read a FAILED row — one 503 lost the message permanently.
    """

    def test_the_first_failure_retries_soon(self):
        retry_at = next_delivery_attempt_at(_at(12), attempts=1)
        assert retry_at == _at(12) + timedelta(seconds=30)

    def test_backoff_grows_with_each_attempt(self):
        delays = [
            next_delivery_attempt_at(_at(12), attempts=n) - _at(12)
            for n in range(1, len(DELIVERY_BACKOFF_SECONDS) + 1)
        ]
        assert delays == sorted(delays)
        assert len(set(delays)) == len(delays)

    def test_attempts_are_eventually_exhausted(self):
        # None is what makes FAILED terminal: the caller stops rescheduling.
        assert next_delivery_attempt_at(_at(12), attempts=MAX_DELIVERY_ATTEMPTS) is None

    def test_every_attempt_before_the_last_gets_a_retry(self):
        for n in range(1, MAX_DELIVERY_ATTEMPTS):
            assert next_delivery_attempt_at(_at(12), attempts=n) is not None

    def test_the_whole_ladder_finishes_within_the_hour(self):
        # A booking confirmation is worth little four hours late, so this
        # ladder is deliberately shallower than the outbox's.
        assert sum(DELIVERY_BACKOFF_SECONDS) <= 3600

    def test_a_nonsensical_attempt_count_does_not_retry(self):
        assert next_delivery_attempt_at(_at(12), attempts=0) is None
        assert next_delivery_attempt_at(_at(12), attempts=-1) is None


class TestTemplateParameters:
    def test_only_declared_parameters_are_passed_through(self):
        # A context assembled from a booking carries names and phone numbers.
        # Sending the lot to a third-party BSP is a quiet data leak.
        params = render_template_params(
            MessageTemplate.QUEUE_CALLED,
            {"customer_name": "Sara", "phone": "+966500000000", "internal_id": "x"},
        )
        assert params == {"customer_name": "Sara"}

    def test_a_missing_parameter_is_refused(self):
        with pytest.raises(ValidationDomainError, match="missing parameters"):
            render_template_params(MessageTemplate.BOOKING_CONFIRMED, {"customer_name": "Sara"})

    def test_values_are_stringified(self):
        params = render_template_params(
            MessageTemplate.QUEUE_JOINED, {"customer_name": "Sara", "position": 3}
        )
        assert params["position"] == "3"


class TestNotificationLifecycle:
    def _notification(self, status=NotificationStatus.PENDING) -> Notification:
        return Notification(
            id="n",
            tenant_id="t",
            customer_id="c",
            channel=NotificationChannel.WHATSAPP,
            template=MessageTemplate.BOOKING_CONFIRMED,
            status=status,
            payload={},
        )

    def test_sent_then_delivered_then_read(self):
        note = self._notification()
        note.mark_sent(provider_message_id="wamid.1", now=_at(9))
        note.mark_delivered()
        note.mark_read()
        assert note.status is NotificationStatus.READ

    def test_a_suppressed_message_is_terminal(self):
        note = self._notification()
        note.suppress(reason="consent_withheld")
        with pytest.raises(ConflictError):
            note.mark_sent(provider_message_id="wamid.1", now=_at(9))

    def test_suppressed_is_distinct_from_failed(self):
        # Collapsing the two would hide a consent problem inside a delivery
        # error metric.
        note = self._notification()
        note.suppress(reason="consent_withheld")
        assert note.status is NotificationStatus.SUPPRESSED
        assert note.status is not NotificationStatus.FAILED

    def test_cannot_be_delivered_before_being_sent(self):
        note = self._notification()
        with pytest.raises(ConflictError):
            note.mark_delivered()
