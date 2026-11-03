"""Production directives written as plain lines in a request: narrator, voice style and background music.

    Narrator: Eric
    Voice style: calm
    Music: library, cinematic minimal      (or: Music: attached / Music: off)

The lines are removed from the text the designer sees; what they chose is reported back, and what could not be
understood is reported too instead of being silently ignored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_LINE = re.compile(r"^\s*(narrator|voice\s*style|voice|music\s*level|music\s*volume|ducking|duck|music|rhythm|loudness|pronounce|pronunciation|راوی|گوینده|سبک\s*صدا|سطح\s*موسیقی|افت\s*موسیقی|موسیقی|ریتم|تلفظ)\s*[:：]\s*(.+?)\s*$", re.I | re.M)
_KIND = {"narrator": "narrator", "voice": "narrator", "راوی": "narrator", "گوینده": "narrator",
         "voicestyle": "style", "سبکصدا": "style", "music": "music", "موسیقی": "music",
         "musiclevel": "level", "musicvolume": "level", "سطحموسیقی": "level", "ducking": "duck", "duck": "duck", "افتموسیقی": "duck",
         "pronounce": "pron", "pronunciation": "pron", "تلفظ": "pron", "rhythm": "rhythm", "ریتم": "rhythm", "loudness": "loudness"}
_STYLE_WORDS = {"natural": "", "neutral": "", "طبیعی": "", "calm": "calm", "soft": "calm", "آرام": "calm", "serious": "serious", "firm": "serious",
                "جدی": "serious", "energetic": "energetic", "excited": "energetic", "پرانرژی": "energetic",
                "reflective": "reflective", "thoughtful": "reflective", "emotional": "reflective", "تأمل‌برانگیز": "reflective"}
_OFF = {"off", "none", "no", "without", "بدون", "نه", "خاموش"}
_ATTACHED = {"attached", "attachment", "my track", "my file", "file", "پیوست", "فایل"}


@dataclass
class Directives:
    narrator: str | None = None        # ElevenLabs voice id; "" means the studio default; None means not stated
    style: str | None = None           # key of brain.localize.VOICE_STYLES
    music: str | None = None           # None = not stated, "off", "attached" or "library"
    music_words: str = ""
    loudness: str | None = None                                # a preset of creative.audio.loudness.PRESETS, or "off"
    rhythm: str | None = None                                  # speech_first | music_first | balanced | cinematic
    music_gain_db: float | None = None                         # level of the music bed when nobody speaks (-40..0)
    ducking_db: float | None = None                            # how far the music drops under speech (0 = no ducking, up to 30)
    pronunciations: dict = field(default_factory=dict)   # written form -> spoken form, e.g. EditorGPT -> ادیتور جی‌پی‌تی
    notes: list[str] = field(default_factory=list)


def _narrator(value: str, notes: list[str]) -> str | None:
    from brain import localize
    wanted = re.sub(r"\s+", " ", value.strip().lower())
    if wanted in {"default", "studio default", "پیش‌فرض", "پیشفرض"}:
        return ""
    for voice_id, name, _ in localize.NARRATORS:
        if voice_id and wanted in {name.lower(), voice_id.lower()}:
            return voice_id
    names = ", ".join(name for voice_id, name, _ in localize.NARRATORS if voice_id)
    notes.append(f"راوی «{value}» پیدا نشد؛ از راوی پیش‌فرض استفاده شد. راوی‌های موجود: {names}")
    return None


_LEVELS = {"quiet": -16.0, "low": -13.0, "medium": -10.0, "loud": -6.0, "آرام": -16.0, "کم": -13.0, "متوسط": -10.0, "بلند": -6.0}
_DUCKS = {"off": 0.0, "none": 0.0, "no": 0.0, "بدون": 0.0, "light": 6.0, "soft": 6.0, "کم": 6.0, "medium": 12.0, "متوسط": 12.0, "strong": 18.0, "heavy": 18.0, "زیاد": 18.0}


def _number_db(value: str) -> float | None:
    found = re.search(r"-?\d+(?:\.\d+)?", value.replace("−", "-"))
    return float(found.group(0)) if found else None


def _level_db(value: str) -> float | None:
    word = value.strip().lower()
    if word in _LEVELS: return _LEVELS[word]
    number = _number_db(value)
    if number is None: return None
    number = -abs(number)                                           # a level is always below full scale: "12 dB" means -12 dB
    return number if -40 <= number <= 0 else None


def _duck_db(value: str) -> float | None:
    word = value.strip().lower()
    if word in _DUCKS: return _DUCKS[word]
    number = _number_db(value)
    return abs(number) if number is not None and abs(number) <= 30 else None


def parse(text: str) -> tuple[str, Directives]:
    found = Directives()
    for match in _LINE.finditer(text or ""):
        kind = _KIND[re.sub(r"\s+", "", match.group(1).lower())]
        value = match.group(2)
        if kind == "narrator":
            found.narrator = _narrator(value, found.notes)
        elif kind == "loudness":
            choice = {"reels": "instagram_reels", "instagram": "instagram_reels", "instagram_reels": "instagram_reels", "tiktok": "tiktok", "youtube": "youtube",
                      "podcast": "podcast", "social": "social_video", "social_video": "social_video", "off": "off", "none": "off", "بدون": "off"}.get(re.sub(r"[\s\-]+", "_", value.strip().lower()))
            if choice: found.loudness = choice
            else: found.notes.append(f"لودنس «{value}» شناخته نشد؛ پیش‌فرض social video استفاده شد. گزینه‌ها: reels, tiktok, youtube, podcast, social, off")
        elif kind == "rhythm":
            mode = re.sub(r"[\s\-]+", "_", value.strip().lower())
            mode = {"speech": "speech_first", "music": "music_first", "گفتار": "speech_first", "موسیقی": "music_first", "متعادل": "balanced", "سینمایی": "cinematic"}.get(mode, mode)
            if mode in {"speech_first", "music_first", "balanced", "cinematic"}: found.rhythm = mode
            else: found.notes.append(f"حالت ریتم «{value}» شناخته نشد؛ speech first استفاده شد. حالت‌ها: speech first, music first, balanced, cinematic")
        elif kind == "level":
            db = _level_db(value)
            if db is None: found.notes.append(f"سطح موسیقی «{value}» شناخته نشد؛ پیش‌فرض (حدود -10 dB) استفاده شد. نمونه: Music level: -12 dB یا quiet / low / medium / loud")
            else: found.music_gain_db = db
        elif kind == "duck":
            db = _duck_db(value)
            if db is None: found.notes.append(f"افت موسیقی «{value}» شناخته نشد؛ پیش‌فرض (12 dB) استفاده شد. نمونه: Ducking: strong / medium / light / off یا 14 dB")
            else: found.ducking_db = db
        elif kind == "pron":
            from creative.audio.persian import parse_dictionary
            entry = parse_dictionary([value])
            if entry: found.pronunciations.update(entry)
            else: found.notes.append(f"تلفظ «{value}» را نفهمیدم؛ قالب درست: Pronounce: Written = Spoken")
        elif kind == "style":
            key = _STYLE_WORDS.get(value.strip().lower()) or next((_STYLE_WORDS[w] for w in re.findall(r"[\w\u0600-\u06FF]+", value.lower()) if w in _STYLE_WORDS), None)
            if key is None:
                found.notes.append(f"سبک صدای «{value}» شناخته نشد؛ سبک طبیعی استفاده شد. سبک‌ها: calm, serious, energetic, reflective, natural")
            else:
                found.style = key
        else:
            lowered = value.strip().lower()
            if lowered in _OFF:
                found.music = "off"
            elif lowered in _ATTACHED:
                found.music = "attached"
            else:
                found.music = "library"
                found.music_words = re.sub(r"^(from\s+)?library\s*[,:\-–—]*\s*", "", value.strip(), flags=re.I)
    clean = _LINE.sub("", text or "")
    return re.sub(r"\n{3,}", "\n\n", clean).strip(), found
