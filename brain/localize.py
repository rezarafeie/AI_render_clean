"""Persian localization of short English videos (e.g. dropshipping reels).

The pipeline keeps the source picture, replaces the spoken English with a
Persian voice-over, covers the burned-in English captions with Persian ones
and ends on a "comment <number>" call to action. This module holds the text
side: sentence splitting, translation with the configured LLM, the CTA
template and Persian voice generation.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_CTA_NUMBER = "31"
# Two caption lines (split at "\n"), as in the reference reels.
CTA_TEMPLATE = 'اگه میخوای ساده و کامل این کارو یاد بگیری\nعدد "{n}" رو برام کامنت کن'
DEFAULT_TITLE_EMOJIS = "🔥😯"
# Persian speech runs at roughly 13-15 characters per second; keep a little
# headroom so a translated line can be spoken inside its English time slot.
CHARS_PER_SECOND = 11.0

_SPLIT_MIN_SECONDS = 4.0
_SPLIT_MIN_PART_SECONDS = 1.2


def _span(words: list[dict]) -> float:
    return float(words[-1]["end"]) - float(words[0]["start"])


def _split_words(words: list[dict]) -> list[list[dict]]:
    """Split at sentence ends, then at commas while a part is still long."""
    parts: list[list[dict]] = [[]]
    for word in words:
        parts[-1].append(word)
        if str(word["w"]).rstrip("\"')").endswith((".", "!", "?")) and word is not words[-1]:
            parts.append([])
    out: list[list[dict]] = []
    for part in (p for p in parts if p):
        out.extend(_split_commas(part))
    return out


def _split_commas(words: list[dict]) -> list[list[dict]]:
    if _span(words) <= _SPLIT_MIN_SECONDS:
        return [words]
    best = None
    for idx, word in enumerate(words[:-1]):
        if not str(word["w"]).endswith(","):
            continue
        left, right = words[: idx + 1], words[idx + 1:]
        if _span(left) >= _SPLIT_MIN_PART_SECONDS and _span(right) >= _SPLIT_MIN_PART_SECONDS:
            balance = abs(_span(left) - _span(right))
            if best is None or balance < best[0]:
                best = (balance, left, right)
    if best is None and (_span(words) > 4.5 or len(words) > 12):
        # ASR often returns two spoken clauses as one sentence without a
        # comma. Prefer a conjunction near the temporal midpoint, otherwise
        # split at the most balanced word boundary.
        candidates = []
        for idx in range(1, len(words)):
            left, right = words[:idx], words[idx:]
            if _span(left) < _SPLIT_MIN_PART_SECONDS or _span(right) < _SPLIT_MIN_PART_SECONDS:
                continue
            marker = _norm_split_word(str(words[idx].get("w", ""))) in {"and", "but", "then", "so", "now"}
            balance = abs(_span(left) - _span(right))
            candidates.append((0 if marker else 1, balance, left, right))
        if candidates:
            _, _, left, right = min(candidates, key=lambda item: (item[0], item[1]))
            best = (0.0, left, right)
    if best is None:
        return [words]
    return _split_commas(best[1]) + _split_commas(best[2])


def _norm_split_word(word: str) -> str:
    return re.sub(r"[^a-z]", "", word.lower())


def split_lines(transcript: dict) -> list[dict]:
    """Turn transcript sentences into caption-sized lines with word timings.

    ASR sentences are split at inner sentence ends (Whisper often merges
    two) and long ones at commas, so each line maps to one on-screen caption
    and one voice clip.
    """
    words = [w for w in transcript.get("words", []) if str(w.get("w", "")).strip()]
    lines: list[dict] = []
    for sentence in transcript.get("sentences", []):
        start, end = float(sentence["start"]), float(sentence["end"])
        members = [w for w in words if start - 0.01 <= float(w["start"]) and float(w["end"]) <= end + 0.01]
        if not members:
            lines.append({"start": start, "end": end, "en": sentence["text"].strip(), "words": []})
            continue
        for part in _split_words(members):
            lines.append({
                "start": float(part[0]["start"]),
                "end": float(part[-1]["end"]),
                "en": " ".join(str(w["w"]).strip() for w in part).strip(),
                "words": [str(w["w"]).strip() for w in part],
            })
    for index, line in enumerate(lines):
        line["i"] = index
    return lines


_SYSTEM = """You localize short English social videos (dropshipping / ecommerce
tutorials) for a Persian-speaking Instagram audience. Return JSON only.

For every input line decide its kind:
- "lyrics": song lyrics, singing, chants or background vocals that are not the narrator explaining something. These keep the original audio and get no Persian line.
- "cta": the closing call to action (e.g. "comment G for a free DM", "follow for more").
- "speech": everything else the narrator says.

For "speech" lines write natural spoken colloquial Persian (محاوره‌ای), like a creator talking to a friend:
- keep brand, site and tool names in Latin script exactly as written (AliExpress, dropship.io, Shopify, Meta Ads, Higgs Field)
- preserve every quantity and price exactly; convert spoken English number words
  to the same Persian digits ("twenty-nine dollars" -> "۲۹ دلار"), never guess or shorten them
- write prices and numbers as digits
- max_chars is a hard limit (the narrator speaks fast and the voice must fit the line's seconds);
  aim for 70-100% of it
- every line still needs its verb and must read naturally; when max_chars is small, write a short
  command that keeps the key action ("کمپین بساز", "بودجه رو بذار ۲۰ دلار"), never a verbless
  fragment like "اکانت Meta Ads"; drop filler words before dropping meaning
- do not add facts that are not in the English
- the English comes from speech recognition and can contain mistakes; fix obvious ones from context
  (e.g. "$2 .33" for a price people pay online after "$1" means $233, "Close your store link" means "Post your store link")

Also write "tutorial_start_i": the line index where the explanatory/tutorial
narration begins. This is the first factual explanation of the product,
opportunity or method — not merely the first imperative step. For example,
"That exact product can be purchased ..." starts the tutorial before the later
instruction "Pull up dropship.io". Reactions, skits and demo-only hooks before
it keep their original audio. If teaching starts immediately, use the first index.

Also write "title": a short, natural Persian adaptation of "source_headline"
when it is supplied. Preserve that headline's actual subject and idea; never
replace it with a generic ecommerce hook. Only fall back to the spoken opening
when source_headline is empty.
It sits above the whole video, so it must make people stop scrolling without
explaining the steps: 4-7 words, about the product or the opportunity, no prices,
no numbers, grammatical and natural. Good examples:
"این محصول این روزا حسابی ترند شده", "همه دارن اینو میخرن", "این محصول داره میترکونه".
And "title_emojis": one or two emojis that fit the hook (e.g. "🔥😯").

Translate only the items in "lines"; "full_script_for_context" is the whole video for context.
When "write_title" is false, return "title" and "title_emojis" as "".

Output schema:
{"title": str, "title_emojis": str, "tutorial_start_i": int, "lines": [{"i": int, "kind": "speech"|"lyrics"|"cta", "fa": str}]}
"fa" is "" for lyrics and cta lines."""


CHUNK_LINES = 6


def translate_caption_cards(lines: list[dict]) -> None:
    """Partition the approved narration across the visible source cards.

    The card text is assembled from contiguous slices of ``line["fa"]``.  The
    model may choose only the slice boundaries; it cannot paraphrase, add or
    remove words.  Consequently the concatenated subtitles are byte-for-byte
    the same words spoken by TTS.
    """
    import hashlib

    pending = []
    for line in lines:
        cards = line.get("covers") or []
        if line.get("kind") in {"lyrics", "cta"} or not cards or not line.get("fa"):
            continue
        tokens = line["fa"].replace("\n", " ").split()
        if len(cards) > len(tokens):
            _coalesce_caption_cards(cards, len(tokens))
        signature = hashlib.sha256(json.dumps(["exact-token-cuts-v1", line["fa"],
                                               [c.get("en", "") for c in cards]],
                                               ensure_ascii=False).encode()).hexdigest()[:16]
        if line.get("caption_text_signature") == signature and all(c.get("fa") for c in cards):
            continue
        pending.append((line, cards, signature))
    if not pending:
        return
    request = [{"i": line["i"], "spoken_en": line.get("en"),
                "approved_tokens": line["fa"].replace("\n", " ").split(),
                "cards": [{"en": c.get("en", ""), "seconds": round(c["end"] - c["start"], 2),
                           "max_chars": max(10, round(c["box"]["w"] / max(.01, c["box"]["h"]) * 1.8))}
                          for c in cards]} for line, cards, _ in pending]
    system = """Choose where to split approved Persian narration across successive visible English caption cards.
Return JSON {"lines":[{"i":integer,"cuts":[integer, ...]}]}.
For N cards return exactly N-1 strictly increasing cut positions. A cut is a token index in approved_tokens,
between 1 and len(approved_tokens)-1. Each card receives the contiguous tokens between adjacent cuts.
Never rewrite, translate, reorder, add or remove a token. Use each card's OCR English, duration and max_chars
only to choose semantic, readable boundaries that align with what is visible in that card."""
    data, _ = _chat_with_fallback(system, json.dumps(request, ensure_ascii=False))
    results = {item.get("i"): item.get("cuts") for item in data.get("lines", []) if isinstance(item, dict)}
    validated = []
    for line, cards, signature in pending:
        tokens = line["fa"].replace("\n", " ").split()
        cuts = results.get(line["i"])
        valid = (isinstance(cuts, list) and len(cuts) == len(cards) - 1
                 and all(isinstance(c, int) for c in cuts)
                 and cuts == sorted(set(cuts))
                 and all(0 < c < len(tokens) for c in cuts))
        if valid:
            points = [0, *cuts, len(tokens)]
            phrases = [" ".join(tokens[points[i]:points[i + 1]]) for i in range(len(cards))]
        else:
            # A malformed model answer must not block rendering or permit a
            # paraphrase. The deterministic fallback still preserves every
            # approved token exactly once.
            phrases = _split_exact_tokens(tokens, len(cards),
                                           [max(.05, c["end"] - c["start"]) for c in cards])
        validated.append((line, cards, signature, phrases))
    for line, cards, signature, phrases in validated:
        for card, phrase in zip(cards, phrases):
            card["fa"] = phrase.strip().replace("\n", " ")
        line["caption_text_signature"] = signature


def _split_exact_tokens(tokens: list[str], count: int, weights: list[float]) -> list[str]:
    """Split tokens into ``count`` non-empty contiguous weighted slices."""
    count = max(1, min(count, len(tokens)))
    total = sum(weights[:count]) or float(count)
    cuts, used = [], 0
    for i in range(count - 1):
        target = round(len(tokens) * sum(weights[:i + 1]) / total)
        used = min(len(tokens) - (count - i - 1), max(used + 1, target))
        cuts.append(used)
    points = [0, *cuts, len(tokens)]
    return [" ".join(tokens[points[i]:points[i + 1]]) for i in range(count)]


def _coalesce_caption_cards(cards: list[dict], target: int) -> None:
    """Merge duplicate animation fragments until every card can own a token."""
    import difflib

    def norm(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.lower())

    while len(cards) > max(1, target):
        candidates = []
        for i in range(len(cards) - 1):
            a, b = norm(cards[i].get("en", "")), norm(cards[i + 1].get("en", ""))
            similarity = difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0
            # Prefer OCR-equivalent neighbours; otherwise absorb the shortest
            # entrance fragment rather than duplicating narration words.
            shortness = 1 / max(.03, cards[i + 1]["end"] - cards[i]["start"])
            candidates.append((similarity * 10 + shortness, i))
        _, index = max(candidates)
        left, right = cards[index], cards[index + 1]
        frames = [*(left.get("frames") or []), *(right.get("frames") or [])]
        merged = {**left, "start": min(left["start"], right["start"]),
                  "end": max(left["end"], right["end"]), "frames": frames}
        if len(str(right.get("en", ""))) > len(str(left.get("en", ""))):
            merged["en"] = right.get("en", "")
        cards[index:index + 2] = [merged]


def _chat_with_fallback(system: str, request: str) -> tuple[dict, object]:
    """Call the configured Arvan text model with bounded retries."""
    from brain.llm import chat_json
    from brain.lm_gateway import configured
    if configured():
        return chat_json(system, request, max_tokens=3000, route="subtitles")

    errors = []
    for attempt in range(3):
        try:
            return chat_json(system, request, max_tokens=3000, temperature=0.3,
                             provider="arvan", timeout_seconds=90)
        except Exception as exc:
            errors.append(f"arvan: {exc}")
            log.warning("translation via Arvan AI attempt %d failed: %s", attempt + 1, exc)
            if re.search(r"\b(?:401|402|403)\b|insufficient[_ ](?:quota|credits)|insufficienttokens", str(exc), re.I):
                break
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("translation failed: " + "; ".join(errors)[-400:])


def translate(lines: list[dict], source_headline: str = "") -> tuple[dict, dict]:
    """Translate lines with the configured LLM. Returns (result, usage).

    Lines go in chunks of ``CHUNK_LINES`` so each request is short; every
    chunk sees the whole English script for context. The first chunk also
    writes the title.
    """
    payload = []
    for k, line in enumerate(lines):
        # A line may use the pause after it: its room runs to the next line.
        room = (lines[k + 1]["start"] if k + 1 < len(lines) else line["end"] + 1.0) - line["start"]
        payload.append({
            "i": line["i"],
            "start": round(line["start"], 2),
            "seconds": round(room, 2),
            "max_chars": max(8, int(room * CHARS_PER_SECOND)),
            "en": line["en"],
        })
    script = [item["en"] for item in payload]
    merged: dict = {"lines": []}
    model, cost = "", 0.0
    for offset in range(0, len(payload), CHUNK_LINES):
        chunk = payload[offset:offset + CHUNK_LINES]
        request = json.dumps({"full_script_for_context": script, "source_headline": source_headline,
                              "lines": chunk,
                              "write_title": offset == 0}, ensure_ascii=False)
        data, usage = _chat_with_fallback(_SYSTEM, request)
        merged["lines"].extend(item for item in data.get("lines", []) if isinstance(item, dict))
        if offset == 0:
            merged["title"], merged["title_emojis"] = data.get("title"), data.get("title_emojis")
            merged["tutorial_start_i"] = data.get("tutorial_start_i")
        model = getattr(usage, "model", model)
        cost += float(usage.cost_estimate)
    return merged, {"model": model, "cost_usd": cost}


def apply_translation(lines: list[dict], data: dict, cta_number: str) -> tuple[list[dict], str, str]:
    """Merge LLM output into lines; returns (lines, title, title_emojis)."""
    by_index = {int(item.get("i", -1)): item for item in data.get("lines", []) if isinstance(item, dict)}
    try:
        tutorial_start = int(data.get("tutorial_start_i"))
    except (TypeError, ValueError):
        tutorial_start = lines[0]["i"] if lines else 0
    valid_indices = {line["i"] for line in lines}
    if tutorial_start not in valid_indices:
        tutorial_start = lines[0]["i"] if lines else 0
    # LLMs sometimes choose the first imperative instruction and skip the
    # factual explanation immediately before it. Rewind through the same
    # continuous narration block, but never into short reaction lines.
    by_pos = {line["i"]: pos for pos, line in enumerate(lines)}
    pos = by_pos.get(tutorial_start, 0)
    while pos > 0:
        prev, current = lines[pos - 1], lines[pos]
        if len(prev.get("words") or prev.get("en", "").split()) < 5:
            break
        if float(current["start"]) - float(prev["end"]) > 2.5:
            break
        tutorial_start = prev["i"]
        pos -= 1
    out = []
    for line in lines:
        item = by_index.get(line["i"], {})
        kind = item.get("kind") if item.get("kind") in {"speech", "lyrics", "cta"} else "speech"
        fa = str(item.get("fa") or "").strip()
        # The established lyrics path preserves source audio and suppresses
        # overlays without changing voice generation or clip placement.
        if line["i"] < tutorial_start:
            kind, fa = "lyrics", ""
        if kind == "speech" and not fa:
            kind = "lyrics"
        out.append({**line, "kind": kind, "fa": fa})
    spoken = [line for line in out if line["kind"] != "lyrics"]
    if spoken and not any(line["kind"] == "cta" for line in out):
        spoken[-1]["kind"] = "cta"
    for line in out:
        if line["kind"] == "cta":
            line["fa"] = cta_text(cta_number)
    title = str(data.get("title") or "").strip() or "این محصول این روزا حسابی ترند شده"
    emojis = str(data.get("title_emojis") or "").strip() or DEFAULT_TITLE_EMOJIS
    return out, title, emojis


def cta_text(number: str) -> str:
    return CTA_TEMPLATE.format(n=str(number).strip() or DEFAULT_CTA_NUMBER)


# --- Persian number words, so TTS reads "31" as «سی و یک» --------------------

_ONES = ["صفر", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه"]
_TEENS = ["ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده"]
_TENS = ["", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"]
_HUNDREDS = ["", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"]
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def number_words(n: int) -> str:
    if n < 0:
        return "منفی " + number_words(-n)
    if n < 10:
        return _ONES[n]
    if n < 20:
        return _TEENS[n - 10]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + (f" و {_ONES[ones]}" if ones else "")
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return _HUNDREDS[hundreds] + (f" و {number_words(rest)}" if rest else "")
    if n < 1_000_000:
        thousands, rest = divmod(n, 1000)
        head = "هزار" if thousands == 1 else f"{number_words(thousands)} هزار"
        return head + (f" و {number_words(rest)}" if rest else "")
    return str(n)


def speakable(text: str) -> str:
    """Spell out integers and drop quotes and line breaks so TTS reads them in Persian."""
    text = re.sub(r"[«»\"]", "", text.translate(_FA_DIGITS))
    text = re.sub(r"\s*\n\s*", " ", text)
    return re.sub(r"(?<![\w.])(\d{1,6})(?![\w.])", lambda m: number_words(int(m.group(1))), text)


# --- Voice --------------------------------------------------------------------

def tts_model() -> str:
    return os.environ.get("LOCALIZE_TTS_MODEL", "eleven_v3").strip() or "eleven_v3"


LIAM_VOICE_ID = "TX3LPaxmHKxFdv7VOQHJ"   # ElevenLabs premade "Liam"


def tts_voice() -> str:
    return os.environ.get("LOCALIZE_VOICE_ID", "").strip() or LIAM_VOICE_ID


def audio_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    return float(out or 0.0)


VOICE_PROVIDERS = ("elevenlabs",)

# Narrators the person can pick per project (ElevenLabs premade voices, each checked to speak Persian through eleven_v3).
# "" is the studio's own casting (the Persian catalogue voice); any other id is used as chosen.
NARRATORS = (
    ("", "پیش‌فرض استودیو", "گوینده‌ی فارسیِ ثبت‌شده در تنظیمات"),
    ("TX3LPaxmHKxFdv7VOQHJ", "Liam", "مرد، جوان و گرم"),
    ("JBFqnCBsd6RMkjVDRZzb", "George", "مرد، قصه‌گو و گرم"),
    ("onwK4e9ZLuTAKqWW03F9", "Daniel", "مرد، عمیق و رسمی"),
    ("pNInz6obpgDQGcFmaJgB", "Adam", "مرد، بم و جدی"),
    ("pqHfZKP75CvOlQylNhV4", "Bill", "مرد، مسن و مستندگو"),
    ("cjVigY5qzO86Huf0OWal", "Eric", "مرد، آرام و قابل‌اعتماد"),
    ("IKne3meq5aSn9XLyUdCD", "Charlie", "مرد، صمیمی و روزمره"),
    ("N2lVS1w4EtoT3dr4eOWO", "Callum", "مرد، گرفته و پرشدت"),
    ("iP95p4xoKVk53GoZ742B", "Chris", "مرد، صمیمی و جذاب"),
    ("EXAVITQu4vr4xnSDxMaL", "Sarah", "زن، نرم و جوان"),
    ("Xb7hH8MSUJpSbSDYk0k2", "Alice", "زن، مطمئن و آموزگار"),
    ("XrExE9yKIg1WjnnlVkGX", "Matilda", "زن، دوستانه و بانشاط"),
)

# How the narrator should sound. eleven_v3 reads bracketed audio tags as direction, not as words.
VOICE_STYLES = {
    "": ("طبیعی", ""),
    "reflective": ("تأمل‌برانگیز، احساسی و تأثیرگذار", "[thoughtful] [emotional] "),
    "calm": ("آرام و صمیمی", "[calm] [softly] "),
    "serious": ("جدی و قاطع", "[serious] "),
    "energetic": ("پرانرژی", "[excited] "),
}


def narrator_ids() -> set[str]:
    return {voice for voice, _, _ in NARRATORS}


def default_voice_provider() -> str:
    return "elevenlabs"


def elevenlabs_characters_left() -> Optional[int]:
    """Remaining ElevenLabs characters this billing period, or None if unknown."""
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        return None
    try:
        import httpx
        from brain.elevenlabs_transport import url as elevenlabs_url

        data = httpx.get(elevenlabs_url("v1/user/subscription"),
                         headers={"xi-api-key": key}, timeout=15).json()
        return int(data["character_limit"]) - int(data["character_count"])
    except Exception:
        return None


def check_voice_budget(texts: list[str], provider: str, cache_dir: Path, voice: str = "", style: str = "") -> None:
    """Fail before rendering when ElevenLabs cannot voice the uncached lines."""
    if provider != "elevenlabs":
        return
    full, _ = narration_script(texts, style)
    needed = 0 if _narration_paths(full, cache_dir, voice)[1].is_file() else len(full)
    left = elevenlabs_characters_left()
    if needed and left is not None and left < needed:
        raise RuntimeError(
            f"ElevenLabs quota is not enough: {max(0, left)} characters left, this video needs {needed}. "
            "Upgrade the ElevenLabs plan or choose another API-enabled ElevenLabs voice."
        )


def _trim_silence(src: Path, dst: Path) -> Path:
    """Drop leading/trailing silence so clips fit the English timing."""
    edge = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05"
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(src),
         "-af", f"{edge},areverse,{edge},areverse", "-ar", "48000", str(dst)],
        capture_output=True,
    )
    if proc.returncode != 0 or not dst.is_file() or audio_duration(dst) < 0.2:
        dst.unlink(missing_ok=True)
        src.replace(dst)
    else:
        src.unlink(missing_ok=True)
    return dst


def _clip_path(text: str, provider: str, out_dir: Path) -> Path:
    provider = "elevenlabs"
    from .speech_policy import identity
    voice = identity(text, tts_voice(), tts_model(), language="fa", context="narration educational")
    digest = hashlib.sha256(f"{provider}|{voice}|{speakable(text)}".encode()).hexdigest()[:16]
    return out_dir / f"line_{provider}_{digest}"


def _cached_clip(text: str, provider: str, out_dir: Path) -> Optional[Path]:
    path = _clip_path(text, provider, out_dir).with_suffix(".wav")
    return path if path.is_file() and path.stat().st_size > 0 else None


def synthesize(text: str, out_dir: Path, provider: str = "elevenlabs") -> tuple[Path, float]:
    """Generate (or reuse) one Persian clip for ``text``; returns (path, seconds)."""
    provider = "elevenlabs"
    out_dir.mkdir(parents=True, exist_ok=True)
    cached = _cached_clip(text, provider, out_dir)
    if cached:
        return cached, audio_duration(cached)
    # A timeout may have spent credit upstream; never resubmit automatically.
    return _synthesize_once(text, out_dir, provider)


def _synthesize_once(text: str, out_dir: Path, provider: str) -> tuple[Path, float]:
    spoken = speakable(text)
    final = _clip_path(text, provider, out_dir).with_suffix(".wav")
    from brain.tts import _generate_elevenlabs

    raw = final.with_name(final.stem + "_raw.mp3")
    _generate_elevenlabs(spoken, str(raw), tts_voice(), tts_model(), language="fa", context="narration educational")
    _trim_silence(raw, final)
    return final, audio_duration(final)


# --- One-take ElevenLabs narration ----------------------------------------------
# Voicing every line separately makes each clip start fresh, so tone and pace
# jump between lines. Instead the whole narration is generated in one request
# with character timings and cut into per-line pieces.

_SENTENCE_END = ".!?؟…"


def narration_script(texts: list[str], style: str = "") -> tuple[str, list[tuple[int, int]]]:
    """Join lines into one speakable text; returns (text, [(start, end) char span per line])."""
    parts: list[str] = []
    spans: list[tuple[int, int]] = []
    pos = 0
    tags = VOICE_STYLES.get(style, VOICE_STYLES[""])[1]
    for raw in texts:
        piece = speakable(raw).strip().rstrip("،,")
        if piece and piece[-1] not in _SENTENCE_END:
            piece += "."
        if piece and tags:
            piece = tags + piece
        if parts:
            pos += 1  # the joining space
        spans.append((pos, pos + len(piece)))
        parts.append(piece)
        pos += len(piece)
    return " ".join(parts), spans


def _cast(text: str, voice: str = "") -> tuple[str, str]:
    """The person's own pick from NARRATORS is used as chosen; otherwise the studio's Persian casting."""
    if voice and voice in narrator_ids():
        return voice, "eleven_v3"
    from .speech_policy import eleven_cast
    return eleven_cast(text, tts_voice(), tts_model(), language="fa", context="narration educational")


def _narration_paths(full: str, out_dir: Path, voice: str = "") -> tuple[Path, Path]:
    voice, model = _cast(full, voice)
    digest = hashlib.sha256(f"casting-v1|{voice}|{model}|{full}".encode()).hexdigest()[:16]
    base = out_dir / f"narration_{digest}"
    return base.with_suffix(".mp3"), base.with_suffix(".json")


from brain.lm_gateway import observe_specialized


@observe_specialized("audio", "elevenlabs-vercel-relay", "v1/text-to-speech/with-timestamps")
def _elevenlabs_with_timestamps(text: str, voice: str = "") -> tuple[bytes, dict]:
    import base64

    import httpx
    from brain.elevenlabs_transport import url as elevenlabs_url

    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ElevenLabs API key is not set")
    voice, model = _cast(text, voice)
    response = httpx.post(
        elevenlabs_url(f"v1/text-to-speech/{voice}/with-timestamps"),
        headers={"xi-api-key": key},
        json={"text": text, "model_id": model, "language_code": "fa"},
        timeout=httpx.Timeout(300.0, connect=20.0),
    )
    if response.status_code == 403:
        raise RuntimeError("ElevenLabs refused the request (HTTP 403); check the network/VPN")
    if response.status_code == 402 or "quota" in response.text.lower():
        raise RuntimeError(f"ElevenLabs quota exceeded (HTTP {response.status_code})")
    response.raise_for_status()
    data = response.json()
    return base64.b64decode(data["audio_base64"]), data["alignment"]


def split_by_alignment(alignment: dict, spans: list[tuple[int, int]], total: float) -> list[tuple[float, float]]:
    """Audio (start, end) of each character span; cuts fall midway between lines."""
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    chars = alignment["characters"]
    voiced = []
    for a, b in spans:
        idx = [k for k in range(a, min(b, len(chars))) if chars[k].strip()]
        voiced.append((starts[idx[0]], ends[idx[-1]]) if idx else None)
    cuts = []
    for k, item in enumerate(voiced):
        if item is None:
            cuts.append((0.0, 0.0))
            continue
        prev = next((v for v in reversed(voiced[:k]) if v), None)
        nxt = next((v for v in voiced[k + 1:] if v), None)
        t0 = (prev[1] + item[0]) / 2 if prev else max(0.0, item[0] - 0.05)
        t1 = (item[1] + nxt[0]) / 2 if nxt else min(total, item[1] + 0.3)
        cuts.append((t0, t1))
    return cuts


def synthesize_narration(texts: list[str], out_dir: Path, voice: str = "", style: str = "") -> list[tuple[Path, float]]:
    """Voice all ``texts`` in ONE ElevenLabs request and cut it per line.

    Returns (clip path, seconds) per text. The full take and its alignment
    are cached, so re-renders of unchanged text spend no credit.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    full, spans = narration_script(texts, style)
    audio, timing = _narration_paths(full, out_dir, voice)
    if not (audio.is_file() and timing.is_file()):
        data, alignment = _elevenlabs_with_timestamps(full, voice)
        audio.write_bytes(data)
        timing.write_text(json.dumps(alignment, ensure_ascii=False))
    alignment = json.loads(timing.read_text())
    total = audio_duration(audio)
    clips = []
    for k, (t0, t1) in enumerate(split_by_alignment(alignment, spans, total)):
        piece = audio.with_name(f"{audio.stem}_{k:02d}.wav")
        if t1 - t0 < 0.05:
            clips.append((piece, 0.0))
            continue
        raw = piece.with_name(piece.stem + "_raw.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(audio), "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}",
                        "-ar", "48000", str(raw)], capture_output=True, check=True)
        _trim_silence(raw, piece)
        clips.append((piece, audio_duration(piece)))
    return clips
