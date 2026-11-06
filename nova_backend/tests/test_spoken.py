"""Times as a Saudi says them on the phone (`app/core/spoken.py`). Pure."""

from datetime import UTC, datetime

import pytest

from app.core.spoken import saudi_clock, saudi_number, saudi_time, speakable


@pytest.mark.parametrize(
    ("hour", "minute", "said"),
    [
        (9, 0, "الساعة تسع الصبح"),
        (10, 15, "الساعة عشر وربع الصبح"),
        (12, 0, "الساعة اثنعش الظهر"),
        (13, 30, "الساعة وحدة ونص الظهر"),
        (16, 30, "الساعة أربع ونص العصر"),
        (16, 45, "الساعة خمس إلا ربع العصر"),
        (18, 20, "الساعة ست وثلث المغرب"),
        (21, 0, "الساعة تسع بالليل"),
        # The period follows the hour said: a quarter to twelve is the noon hour.
        (11, 45, "الساعة اثنعش إلا ربع الظهر"),
        (0, 0, "الساعة اثنعش بالليل"),
        (10, 7, "الساعة عشر وسبع دقايق الصبح"),
    ],
)
def test_the_clock_reads_as_spoken(hour: int, minute: int, said: str):
    assert saudi_clock(hour, minute) == said


def test_today_tomorrow_and_the_day_after_are_said_as_such():
    now = datetime(2026, 10, 22, 6, 0, tzinfo=UTC)  # Thursday 09:00 in Riyadh
    at_four = datetime(2026, 10, 22, 13, 0, tzinfo=UTC)  # 16:00 in Riyadh
    assert saudi_time(at_four, timezone="Asia/Riyadh", now=now) == "اليوم الساعة أربع العصر"
    tomorrow = at_four.replace(day=23)
    assert saudi_time(tomorrow, timezone="Asia/Riyadh", now=now) == "بكرة الساعة أربع العصر"
    after = at_four.replace(day=24)
    assert saudi_time(after, timezone="Asia/Riyadh", now=now).startswith("بعد بكرة")
    later = at_four.replace(day=27)
    assert saudi_time(later, timezone="Asia/Riyadh", now=now).startswith("يوم الثلاثاء")


def test_the_branchs_clock_decides_the_day():
    """23:30 UTC is already the next morning in Riyadh."""
    now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    late = datetime(2026, 10, 22, 23, 30, tzinfo=UTC)
    assert saudi_time(late, timezone="Asia/Riyadh", now=now) == "بكرة الساعة ثنتين ونص بالليل"


@pytest.mark.parametrize(
    ("n", "said"),
    [
        (0, "صفر"),
        (3, "ثلاثة"),
        (11, "إحدعش"),
        (21, "واحد وعشرين"),
        (100, "مية"),
        (105, "مية وخمسة"),
        (150, "مية وخمسين"),
        (200, "ميتين"),
        (600, "ست مية"),
        (1250, "ألف وميتين وخمسين"),
        (3400, "ثلاث آلاف وأربع مية"),
    ],
)
def test_numbers_are_said_in_saudi_words(n: int, said: str):
    assert saudi_number(n) == said


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("موعدكم الساعة 16:30.", "موعدكم الساعة أربع ونص العصر."),
        ("السعر 150 SAR", "السعر مية وخمسين ريال"),
        ("السعر \u0661\u0665\u0660 ر.س", "السعر مية وخمسين ريال"),
        ("SAR 75 فقط", "خمسة وسبعين ريال فقط"),
        ("المبلغ 1,250.00 ريال", "المبلغ ألف وميتين وخمسين ريال"),
        ("السعر 99.50 ريال", "السعر تسعة وتسعين ونص ريال"),
        ("خصم 10%", "خصم عشرة بالمية"),
        # "4:30" alone does not say which part of the day: no period is guessed.
        ("الساعة 4:30", "الساعة أربع ونص"),
        ("**الخميس**\n- متاح 🎉 https://nova.sa/b/x", "الخميس متاح"),
        # Phone numbers, dates and odd fractions keep their digits.
        (
            "رقمكم 0501234567 وتاريخ 23/10، وقيمته 12.75",
            "رقمكم 0501234567 وتاريخ 23/10، وقيمته 12.75",
        ),
        ("أبشروا، الساعة أربع ونص العصر.", "أبشروا، الساعة أربع ونص العصر."),
    ],
)
def test_arabic_text_is_made_speakable(text: str, said: str):
    assert speakable(text, locale="ar") == said
    assert speakable(said, locale="ar") == said, "speaking it twice changes nothing"


def test_english_keeps_its_digits_for_unifonic_s_voice():
    assert speakable("**At 16:30** for 150 SAR 😀", locale="en") == "At 16:30 for 150 SAR"
