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

_LINE = re.compile(r"^\s*(narrator|voice\s*style|voice|music|pronounce|pronunciation|راوی|گوینده|سبک\s*صدا|موسیقی|تلفظ)\s*[:：]\s*(.+?)\s*$", re.I | re.M)
_KIND = {"narrator": "narrator", "voice": "narrator", "راوی": "narrator", "گوینده": "narrator",
         "voicestyle": "style", "سبکصدا": "style", "music": "music", "موسیقی": "music",
         "pronounce": "pron", "pronunciation": "pron", "تلفظ": "pron"}
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


def parse(text: str) -> tuple[str, Directives]:
    found = Directives()
    for match in _LINE.finditer(text or ""):
        kind = _KIND[re.sub(r"\s+", "", match.group(1).lower())]
        value = match.group(2)
        if kind == "narrator":
            found.narrator = _narrator(value, found.notes)
        elif kind == "pron":
            from creative.audio.persian import parse_dictionary
            entry = parse_dictionary([value])
            if entry: found.pronunciations.update(entry)
            else: found.notes.append(f"تلفظ «{value}» را نفهمیدم؛ قالب درست: Pronounce: Written = Spoken")
        elif kind == "style":
            key = _STYLE_WORDS.get(value.strip().lower())
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
