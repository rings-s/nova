"""Times, numbers and text as a Saudi says them aloud, for Sara on the phone (ADR-0017).

A text-to-speech voice reads "16:30" as "ستة عشر وثلاثون", which no one in
Riyadh says. These give the words a caller expects: "بكرة الساعة أربع ونص
العصر". `speakable` does the same for whatever the model wrote, which the
tools' spoken times do not cover. Pure: no framework, no I/O.
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_HOURS = (
    "اثنعش",
    "وحدة",
    "ثنتين",
    "ثلاث",
    "أربع",
    "خمس",
    "ست",
    "سبع",
    "ثمان",
    "تسع",
    "عشر",
    "إحدعش",
)
_WEEKDAYS = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")

#: Minutes past the hour as said aloud. A time on any other minute is rare on a
#: salon's 15-minute grid and is said as "و٧ دقايق" instead.
_PAST = {
    0: "",
    5: " وخمس",
    10: " وعشر",
    15: " وربع",
    20: " وثلث",
    25: " ونص إلا خمس",
    30: " ونص",
    35: " ونص وخمس",
}
#: Minutes before the next hour.
_TO = {40: " إلا ثلث", 45: " إلا ربع", 50: " إلا عشر", 55: " إلا خمس"}


def _period(hour: int) -> str:
    """The part of the day a Saudi names after the hour (24-hour clock in)."""
    if 4 <= hour < 12:
        return "الصبح"
    if 12 <= hour < 15:
        return "الظهر"
    if 15 <= hour < 18:
        return "العصر"
    if 18 <= hour < 20:
        return "المغرب"
    return "بالليل"


def _clock_words(hour: int, minute: int) -> tuple[int, str]:
    """The hour said (the next one for "إلا ربع") and the words for it."""
    if minute in _TO:
        said_hour, rest = (hour + 1) % 24, _TO[minute]
    else:
        said_hour = hour
        rest = _PAST.get(minute, f" و{saudi_number(minute, counted=True)} دقايق")
    return said_hour, f"{_HOURS[said_hour % 12]}{rest}"


def saudi_clock(hour: int, minute: int) -> str:
    """`(16, 30)` -> "الساعة أربع ونص العصر"."""
    said_hour, words = _clock_words(hour, minute)
    # The period follows the hour said, so 11:45 is "اثنعش إلا ربع الظهر".
    return f"الساعة {words} {_period(said_hour)}"


def saudi_time(moment: datetime, *, timezone: str, now: datetime | None = None) -> str:
    """A moment as Sara says it, in the branch's clock: "بكرة الساعة عشر الصبح".

    With `now`, today, tomorrow and the day after are said as such; any other
    day by its weekday name.
    """
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("Asia/Riyadh")
    local = moment.astimezone(zone)
    day = f"يوم {_WEEKDAYS[local.weekday()]}"
    if now is not None:
        days_ahead = (local.date() - now.astimezone(zone).date()).days
        day = {0: "اليوم", 1: "بكرة", 2: "بعد بكرة"}.get(days_ahead, day)
    return f"{day} {saudi_clock(local.hour, local.minute)}"


_UNITS = ("صفر", "واحد", "اثنين", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة", "عشرة")
#: Before a counted noun ("سبع دقايق", "ثلاث مية") 3 to 10 take the short form.
_COUNTED = {3: "ثلاث", 4: "أربع", 5: "خمس", 6: "ست", 7: "سبع", 8: "ثمان", 9: "تسع", 10: "عشر"}
_TEENS = ("إحدعش", "اثنعش", "ثلطعش", "أربعطعش", "خمسطعش", "سطعش", "سبعطعش", "ثمنطعش", "تسعطعش")
_TENS = ("", "", "عشرين", "ثلاثين", "أربعين", "خمسين", "ستين", "سبعين", "ثمانين", "تسعين")
#: Above this a number is left as digits: an account or phone number, not an amount.
MAX_SPOKEN_NUMBER = 9999


def saudi_number(n: int, *, counted: bool = False) -> str:
    """0 to 9999 in Saudi words: 150 -> "مية وخمسين", 1250 -> "ألف وميتين وخمسين"."""
    if not 0 <= n <= MAX_SPOKEN_NUMBER:
        raise ValueError(f"{n} is not a number Sara says in words")
    if n <= 10:
        return _COUNTED.get(n, _UNITS[n]) if counted else _UNITS[n]
    if n < 20:
        return _TEENS[n - 11]
    if n < 100:
        tens, unit = divmod(n, 10)
        return f"{_UNITS[unit]} و{_TENS[tens]}" if unit else _TENS[tens]
    parts: list[str] = []
    thousands, rest = divmod(n, 1000)
    if thousands:
        parts.append({1: "ألف", 2: "ألفين"}.get(thousands) or f"{_COUNTED[thousands]} آلاف")
    hundreds, rest = divmod(rest, 100)
    if hundreds:
        parts.append({1: "مية", 2: "ميتين"}.get(hundreds) or f"{_COUNTED[hundreds]} مية")
    if rest:
        parts.append(saudi_number(rest))
    return " و".join(parts)


#: Arabic-Indic digits and the Arabic decimal separator, as ASCII.
_EASTERN_DIGITS = str.maketrans(
    "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669\u066b", "0123456789."
)
_URL = re.compile(r"https?://\S+|www\.\S+")
#: Pictographs, dingbats, flags, and the joiners and selectors that build emoji.
_EMOJI = re.compile("[\U0001f000-\U0001faff\u2600-\u27bf\u2b00-\u2bff\ufe0f\u200d]")
_CLOCK = re.compile(r"(?:الساعة\s*)?(?<![\d:])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])")
_RIYAL = r"(?:SAR|ر\.\s?س\.?|ريال سعودي)"
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")
# Not next to "/", "-" or another digit: dates and phone numbers stay as written.
_NUMBER = re.compile(r"(?<![\d/.\-])(\d+)(?:\.(\d+))?(?![\d/\-]|\.\d)")


def _said_clock(match: re.Match[str]) -> str:
    hour, minute = int(match.group(1)), int(match.group(2))
    said_hour, words = _clock_words(hour, minute)
    if hour == 0 or hour > 12:
        # A 24-hour time says which part of the day it is; "4:30" does not.
        return f"الساعة {words} {_period(said_hour)}"
    return f"الساعة {words}"


def _said_number(match: re.Match[str]) -> str:
    whole, fraction = match.group(1), match.group(2) or ""
    if (len(whole) > 1 and whole.startswith("0")) or int(whole) > MAX_SPOKEN_NUMBER:
        return match.group(0)
    words = saudi_number(int(whole))
    if fraction.strip("0") == "":
        return words
    if fraction.rstrip("0") == "5":
        return f"{words} ونص"
    return match.group(0)


def speakable(text: str, *, locale: str) -> str:
    """Text as it should be read aloud on a phone line.

    For any language: no markdown, list marks, line breaks, links or emoji,
    which a voice reads out or stumbles on. In Arabic also: times, riyals and
    amounts in Saudi words ("الساعة 16:30" -> "الساعة أربع ونص العصر",
    "150 SAR" -> "مية وخمسين ريال"). Dates, phone numbers and codes keep their
    digits. Text already in words comes back unchanged.
    """
    kept = _EMOJI.sub("", _URL.sub("", text.replace("*", "").replace("#", "").replace("`", "")))
    lines = [line.strip().lstrip("-•").strip() for line in kept.splitlines()]
    said = " ".join(line for line in lines if line)
    if locale[:2] == "ar":
        said = said.translate(_EASTERN_DIGITS)
        said = _CLOCK.sub(_said_clock, said)
        said = _THOUSANDS.sub("", said)
        said = re.sub(rf"{_RIYAL}\s*(\d+(?:\.\d+)?)", r"\1 ريال", said)
        said = re.sub(rf"(\d+(?:\.\d+)?)\s*{_RIYAL}", r"\1 ريال", said)
        said = re.sub(r"(\d+)\s*%", r"\1 بالمية", said)
        said = _NUMBER.sub(_said_number, said)
    return re.sub(r"\s+([،.؟!,?])", r"\1", re.sub(r"\s{2,}", " ", said)).strip()
