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


def spell_numbers(text: str) -> str:
    """Whole numbers (any digit script) and N% become words. Decimals, dates and phone-like digit runs are left alone."""
    latin = text.translate(_DIGITS)
    def number(match: re.Match) -> str:
        raw = match.group(0)
        start, end = match.span()
        before, after = latin[start - 1:start], latin[end:end + 1]
        if after in {".", ","} and latin[end + 1:end + 2].isdigit() or before in {".", ",", "/", ":", "-"} or after in {"/", ":"} or len(raw) > 12:
            return text[start:end]                       # a decimal, date, time or long code: keep as written
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
