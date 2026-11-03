"""Persian narration text: what is read aloud is derived from the script, which is never overwritten.

`speakable()` returns the text for a speech provider: letter variants unified, digits and percentages spelled out in
Persian words, and the project's pronunciation entries applied. Entries are explicit only; nothing is transliterated
on its own, because a respelling does not guarantee a better pronunciation.
"""
from __future__ import annotations

import re

_ARABIC_TO_PERSIAN = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"})
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_ONES = ["صفر", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه", "ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده",
         "شانزده", "هفده", "هجده", "نوزده"]
_TENS = ["", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"]
_HUNDREDS = ["", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"]
_SCALES = [(10**12, "تریلیون"), (10**9, "میلیارد"), (10**6, "میلیون"), (10**3, "هزار")]
_PERSIAN_LETTER = re.compile(r"[؀-ۿ]")


def is_persian(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(1 for c in letters if _PERSIAN_LETTER.match(c)) / len(letters) > 0.4


def number_words(value: int) -> str:
    """A non-negative whole number in Persian words: 1205 -> «هزار و دویست و پنج»."""
    if value < 0:
        return "منفی " + number_words(-value)
    if value < 20:
        return _ONES[value]
    if value < 100:
        tens, rest = divmod(value, 10)
        return _TENS[tens] + (" و " + _ONES[rest] if rest else "")
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        return _HUNDREDS[hundreds] + (" و " + number_words(rest) if rest else "")
    for size, name in _SCALES:
        if value >= size:
            count, rest = divmod(value, size)
            head = name if (size == 1000 and count == 1) else f"{number_words(count)} {name}"
            return head + (" و " + number_words(rest) if rest else "")
    raise ValueError("number out of range")


def unify_letters(text: str) -> str:
    return text.translate(_ARABIC_TO_PERSIAN)


_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
_JALALI_DATE = re.compile(r"(?<![\d/.])(1[34]\d{2})/(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])(?![\d/])")
_TIME = re.compile(r"(?<![\d:/.])([01]?\d|2[0-3]):([0-5]\d)(?![\d:/])")
_DECIMAL = re.compile(r"(?<![\d.])(\d+)\.(\d+)(?![\d.])")
_DIGIT_RUN = re.compile(r"(?<![\d.,])(?:0\d+|\d{10,})(?![\d.,])")


def ordinal(day: int) -> str:
    """The day of a month as spoken: 1 «اول», 3 «سوم», 12 «دوازدهم», 23 «بیست و سوم», 30 «سی‌ام»."""
    if day == 1: return "اول"
    words = number_words(day)
    if words.endswith("سه"): return words[:-2] + "سوم"
    if words == "سی": return "سی‌ام"
    return words + "م"


def digits_one_by_one(digits: str) -> str:
    return " ".join(_ONES[int(d)] for d in digits)


def spell_numbers(text: str) -> str:
    """Whole numbers (any digit script) and N% become words, as do Jalali dates (1403/05/12), times (14:30), simple decimals (3.5) and
    phone-like digit runs (read digit by digit). A Gregorian-looking date, a version number such as 1.2.3 and a code with other
    separators are left as written: guessing how to read them would be worse than leaving them."""
    latin = text.translate(_DIGITS)
    if re.search(r"\d", latin):
        latin = _JALALI_DATE.sub(lambda m: f"{ordinal(int(m.group(3)))} {_MONTHS[int(m.group(2)) - 1]} {number_words(int(m.group(1)))}", latin)
        latin = _TIME.sub(lambda m: number_words(int(m.group(1))) + (f" و {number_words(int(m.group(2)))} دقیقه" if m.group(2) != "00" else ""), latin)
        latin = _DECIMAL.sub(lambda m: f"{number_words(int(m.group(1)))} ممیز " + (digits_one_by_one(m.group(2)) if m.group(2).startswith("0") or len(m.group(2)) > 3 else number_words(int(m.group(2)))), latin)
        latin = _DIGIT_RUN.sub(lambda m: digits_one_by_one(m.group(0)), latin)
    def number(match: re.Match) -> str:
        raw = match.group(0)
        start, end = match.span()
        before, after = latin[start - 1:start], latin[end:end + 1]
        if after in {".", ","} and latin[end + 1:end + 2].isdigit() or before in {".", ",", "/", ":", "-"} or after in {"/", ":"} or len(raw) > 12:
            return raw                                   # a code with other separators, a version number: kept as written
        grouped = raw.replace(",", "")
        words = number_words(int(grouped))
        return words + (" درصد" if after in {"%", "٪"} else "")
    out = re.sub(r"\d{1,3}(?:,\d{3})+|\d+", number, latin)
    return out.replace("%", "").replace("٪", "")


def apply_pronunciations(text: str, entries: dict[str, str]) -> str:
    """Replace whole-word occurrences (longest entry first) with the stated spoken form."""
    for written in sorted(entries, key=len, reverse=True):
        spoken = entries[written]
        if written and spoken:
            text = re.sub(rf"(?<![\w؀-ۿ]){re.escape(written)}(?![\w؀-ۿ])", spoken, text)
    return text


def speakable(text: str, pronunciations: dict[str, str] | None = None) -> str:
    """The text to send to a speech provider. English-only text is returned untouched except for the dictionary."""
    spoken = apply_pronunciations(text, pronunciations or {})
    if not is_persian(spoken):
        return spoken
    return re.sub(r"[ \t]+", " ", spell_numbers(unify_letters(spoken))).strip()


def parse_dictionary(lines: list[str]) -> dict[str, str]:
    """'EditorGPT = ادیتور جی‌پی‌تی' lines to a dictionary; malformed lines are ignored."""
    entries = {}
    for line in lines:
        if "=" in line:
            written, spoken = (part.strip() for part in line.split("=", 1))
            if written and spoken and len(written) <= 60 and len(spoken) <= 120:
                entries[written] = spoken
    return entries
