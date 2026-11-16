"""Pronunciation pass for Persian narration before it goes to the speech model (ElevenLabs v3).

The voice reads unvowelled Persian by guessing: homographs come out wrong («مرتب» as «مَرتَب», «برنده» as «بُرنده»), and foreign names written in Persian
letters («شاپ‌پی», «پی‌استک») are read as Persian words. Two layers fix this:
1. LEXICON: words the studio has heard wrong, always written with the marks that make them unambiguous (whole words only).
2. A model pass over the film's lines: minimal diacritics ONLY on ambiguous words, and every Latin or transliterated foreign word rewritten in Persian
   letters as it is pronounced, with marks. A line the model changed beyond that (other words, order, meaning) is ignored and the lexicon version is kept.
The person's own fixes («مرتب = مُرَتَّب», studio pronunciation dictionary) are applied before this and are never undone.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from difflib import SequenceMatcher
from pathlib import Path

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# written form (no marks) -> spoken form with the marks that remove the ambiguity
LEXICON: dict[str, str] = {
    "مرتب": "مُرَتَّب", "مرتبا": "مُرَتَّباً", "برنده": "بَرَنده", "برندگان": "بَرَندِگان", "بازنده": "بازَنده", "سرمایه": "سَرمایه",
    "مشتری": "مُشتَری", "مشتری‌ها": "مُشتَری‌ها", "مدل": "مُدِل", "مدیر": "مُدیر", "مدیرعامل": "مُدیرعامِل", "توسعه": "توسِعه", "توسعه‌دهنده": "توسِعه‌دَهَنده",
    "توسعه‌دهنده‌ها": "توسِعه‌دَهَنده‌ها", "کسب": "کَسب", "کسب‌وکار": "کَسب‌وکار", "درآمد": "دَرآمَد", "ضرر": "ضَرَر", "رشد": "رُشد", "سهم": "سَهم",
    "سهام": "سَهام", "ارز": "اَرز", "ارزش": "اَرزِش", "دلار": "دُلار", "تراکنش": "تَراکُنِش", "پلتفرم": "پِلَتفُرم", "اپ": "اَپ", "اپلیکیشن": "اَپلیکِیشِن",
    "استارتاپ": "اِستارتاپ", "برند": "بِرَند", "مارکتینگ": "مارکِتینگ", "تبلیغ": "تَبلیغ", "تبلیغات": "تَبلیغات", "شرکت": "شِرکَت", "بین‌المللی": "بِین‌اُلمِلَلی",
    "مستقل": "مُستَقِل", "متخصص": "مُتِخَصِّص", "محصول": "مَحصول", "محصولات": "مَحصولات", "مخاطب": "مُخاطَب", "مشکل": "مُشکِل", "اول": "اَوَّل", "دوم": "دُوُّم",
}
# English words a Persian narration often borrows: the spoken Persian form (a Latin word is otherwise read letter by letter or with English vowels at random)
ENGLISH: dict[str, str] = {
    "pay": "پِی", "shop": "شاپ", "store": "اِستور", "app": "اَپ", "online": "آنلاین", "startup": "اِستارتاپ", "freelance": "فِریلَنس", "freelancer": "فِریلَنسِر",
    "dropshipping": "دِراپ‌شیپینگ", "google": "گوگِل", "amazon": "آمازون", "apple": "اَپِل", "paypal": "پِی‌پَل", "stripe": "اِسترایپ", "shopify": "شاپیفای",
    "youtube": "یوتیوب", "instagram": "اینستاگرام", "tiktok": "تیک‌تاک", "ai": "اِی‌آی", "ceo": "سی‌ای‌او", "ipo": "آی‌پی‌او", "saas": "سَس", "b2b": "بی‌تو‌بی",
}
_MARKS = re.compile(r"[ً-ْٰـ]")
_EDGE = r"(?<![\w؀-ۿ‌])", r"(?![\w؀-ۿ‌])"


def bare(text: str) -> str:
    return _MARKS.sub("", text or "")


def apply_lexicon(text: str) -> str:
    """Lexicon spoken forms for whole unvowelled words (a word the writer already marked is left as written) and known English words."""
    for written in sorted(LEXICON, key=len, reverse=True):
        text = re.sub(_EDGE[0] + re.escape(written) + _EDGE[1], LEXICON[written], text)
    for written in sorted(ENGLISH, key=len, reverse=True):
        text = re.sub(r"(?<![A-Za-z])" + re.escape(written) + r"(?![A-Za-z])", ENGLISH[written], text, flags=re.I)
    return text


GUIDE = """You prepare Persian narration lines for a Persian text-to-speech voice (ElevenLabs v3). The voice reads unvowelled Persian by guessing, so it misreads
homographs and foreign words. Return the SAME lines with only these changes:
1. Add Persian diacritics (fatha, kasra, damma, tashdid, sukun) ONLY on words whose reading is ambiguous or commonly misread without them (مُرَتَّب not مرتب,
   بَرَنده, مُدِل, کُرد/کَرد, مِلک/مُلک, سَهم, دُوُّم, مُتِخَصِّص, rare or technical words, Arabic loanwords). Mark the whole word, correctly. Leave clear everyday words alone.
   Keep the ezafe kasra already written (فروشگاهِ) and add it where the phrase would be misread without it.
2. Every foreign word or name - written in Latin letters OR already transliterated into Persian letters - is written in Persian letters exactly as it is
   pronounced in its own language, with diacritics on every vowel that is not obvious: «Shop Pay» / «شاپ‌پی» → «شاپ پِی», «Paystack» / «پی‌استک» → «پِی‌اِستَک»,
   «Ruby on Rails» → «روبی آن رِیلز», «Lütke» → «لوتکه», «Daniel Weinand» → «دانیِل وای‌نَند». Brand names keep their usual Persian spelling when one exists (گوگل، آمازون).
3. Nothing else: never add, remove, reorder or replace a Persian word, never change punctuation, the «...» pauses, numbers written in words or half-spaces.
Return strict JSON {"lines": ["...", ...]} with exactly as many lines as given, in the same order."""


class _Lines(BaseModel):
    lines: list[str] = Field(default_factory=list)


def _cache_dir() -> Path:
    parents = Path(__file__).resolve().parents
    shared = parents[2] / "assets" / "models" if len(parents) > 2 else Path("/nonexistent")
    base = shared if shared.is_dir() and os.access(shared, os.W_OK) else Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "editorgpt"
    return base / "pronounce"


def _persian_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[؀-ۿ‌]+", bare(text)) if w.strip("‌")]


def acceptable(before: str, after: str) -> bool:
    """The model's line keeps the Persian words of the original (marks aside): at most a few changed tokens, which must be the foreign ones it rewrote."""
    if not after.strip():
        return False
    a, b = _persian_words(before), _persian_words(after)
    if not a:
        return True
    ratio = SequenceMatcher(None, a, b).ratio()
    latin = len(re.findall(r"[A-Za-z]+", before))
    return ratio >= 0.86 or (latin and ratio >= 0.7) or abs(len(a) - len(b)) <= 1 and ratio >= 0.8


def prepare(lines: list[str], *, route: str = "", notes=None) -> list[str]:
    """The lines as the voice should read them: the lexicon, then the model pass (cached per text). A model failure keeps the lexicon version."""
    persian = re.compile(r"[\u0600-\u06FF]")
    base = [apply_lexicon(line) if persian.search(line or "") else line for line in lines]
    if not any(persian.search(line or "") for line in lines):
        return base                                           # an English narration is read as written
    if not route or not any(line.strip() for line in lines):
        return base
    key = hashlib.sha256(json.dumps([route, GUIDE, base], ensure_ascii=False).encode()).hexdigest()[:16]
    cache = _cache_dir() / f"{key}.json"
    if cache.is_file():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    try:
        from creative import llm
        from app.studio_activity import describe
        with describe("pronunciation", "دارم تلفظ کلمه‌های دوپهلو و اسم‌های خارجی متن را برای گوینده اعراب‌گذاری می‌کنم."):
            got = llm.ask(_Lines, GUIDE, json.dumps({"lines": base}, ensure_ascii=False), route=route, tokens=6000, attempts=2).lines
    except Exception as exc:
        log.warning("pronunciation pass failed: %s", str(exc)[:200])
        return base
    out = []
    for before, after in zip(base, list(got) + [""] * len(base)):
        after = re.sub(r"[ \t]+", " ", (after or "").strip())
        out.append(after if acceptable(before, after) else before)
        if after and out[-1] is before:
            log.info("pronunciation pass changed a line too much; kept: %s", before[:80])
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return out
