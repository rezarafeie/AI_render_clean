"""Intro engine 2 — Reel: a 15-second motion showreel (1920x1080, 60 fps, music and effects); every cut sits on the music's beat grid. Template: kit/src/Reel.tsx."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

KIND, WIDTH, HEIGHT, FPS, MUSIC, MUSIC_GAIN, FADE = "reel", 1920, 1080, 60, "reel", 0.5, 0.6


class Content(BaseModel):
    model_config = ConfigDict(extra="ignore")
    questions: list[str] = Field(default_factory=list)
    brand: str = ""
    hud: str = ""                      # the small line at the top right of every scene
    tagline: str = ""
    url: str = ""
    opener: list[str] = Field(default_factory=list)       # three giant words that make one sentence («بگو» «تا» «بسازم»)
    opener_note: str = ""              # a tiny dictionary-style note under the third word
    shapes: list[str] = Field(default_factory=list)       # three words, one beside each shape (circle, square, triangle)
    shapes_caption: str = ""
    claim_1: str = ""                  # over the easing curve
    claim_1_note: str = ""
    claim_2: str = ""                  # over the dot field
    field_label: str = ""
    blink: list[str] = Field(default_factory=list)        # two giant words in the tunnel («پلک» «نزن»)
    words: list[str] = Field(default_factory=list)        # three last giant words («منحنی» «سرعت» «سلیقه»)
    count_note: str = ""
    facts: list[dict] = Field(default_factory=list)
    mascot_shape: str = "circle"


EXAMPLE = {
    "brand": "ادیتورجی‌پی‌تی", "hud": "ادیتورجی‌پی‌تی — شوریل موشن ۱۴۰۵", "tagline": "ادیتور ویدیو با هوش مصنوعی — فقط بگو چه می‌خواهی", "url": "editor.rafiei.co",
    "opener": ["بگو", "تا", "بسازم"], "opener_note": "(فعل) از یک پیام، یک ویدیوی آماده درآوردن", "shapes": ["برش", "کپشن", "موشن"], "shapes_caption": "موتورها",
    "claim_1": "زمان‌بندی، روی کلمه.", "claim_1_note": "هر برش، روی کلمهٔ گوینده", "claim_2": "همه‌اش کد. بدون استوک.", "field_label": "میدان /",
    "blink": ["پلک", "نزن"], "words": ["منحنی", "سرعت", "سلیقه"], "count_note": "فشردگی و کشش — اصل شمارهٔ", "mascot_shape": "spark",
    "facts": [{"claim": "کپشن‌ها روی کلمهٔ گوینده می‌نشینند", "source": "README"}],
}

GUIDE = """THE REEL INTRO (landscape 1920x1080, 15 s, 60 fps, music only): a motion showreel: a 3-2-1 bounce, three giant words that make one sentence,
three shapes each beside one word, an easing curve under a claim, a field of dots under a second claim, a tunnel with two giant words, three last
giant words, then the signature (brand, tagline, address). Giant words fill the frame: SHORT words only.
Fill this JSON (Persian):
- brand: the product's name written as one mark. hud: one small line «<brand> — <what this reel is>» (max 34 characters).
- tagline: one line, max 52 characters. url: without https://.
- opener: exactly 3 words, each at most 5 letters, that read as one short sentence about what the product does for the person.
- opener_note: a dictionary-style gloss of the third word, max 44 characters, starting with its part of speech in parentheses.
- shapes: exactly 3 nouns, each at most 6 letters: three things the product does (from the FACTS). shapes_caption: what the three are, one word.
- claim_1 and claim_2: two short claims (max 22 characters each, two fragments with a full stop each) that the FACTS support. claim_1_note: max 28 characters.
- field_label: two or three characters of label before the dot count (for example «میدان /»).
- blink: exactly 2 words of at most 4 letters each: a two-word command to the viewer.
- words: exactly 3 words of at most 6 letters each: the qualities the product stands for; the last one is the punchline.
- count_note: a tiny caption under the countdown (max 28 characters), written so a number can follow it.
- mascot_shape: the simple shape closest to the brand's OWN mark: spark | circle | square | drop | hex | diamond | cloud.
- facts: every claim the reel shows with its source."""


def plan(content: Content, grid: dict) -> tuple[dict, list[dict], float]:
    first, period = float(grid["first"]), float(grid["period"])

    def B(n: int) -> float:
        return first + period * (n - 1)

    total = round(B(29) + 3 * period, 3)
    ev: list[dict] = []

    def e(t: float, k: str, g: float = 0.6) -> None:
        ev.append({"t": round(t, 3), "k": k, "g": g})

    for n in (1, 2, 3):
        e(B(n), "thump", 0.7)
    e(B(4), "hit", 0.8); e(B(5), "hit", 0.7); e(B(6), "whoosh", 0.8)
    for n in (7, 9, 11):
        e(B(n), "pop", 0.7)
    e(B(13), "tick", 0.6); e(B(17) - 0.3, "riser", 0.5); e(B(20), "whoosh", 0.9); e(B(21), "hit", 0.8); e(B(23), "hit", 0.8)
    e(B(25), "whoosh", 0.7); e(B(26), "whoosh", 0.9); e(B(27), "hit", 0.9); e(B(30), "ding", 0.8)
    return {"grid": {"first": first, "period": period}, "total": total}, ev, total


def still_times(timing: dict) -> list[tuple[str, float]]:
    g = timing["grid"]

    def B(n: float) -> float:
        return g["first"] + g["period"] * (n - 1)

    return [("count", B(3) + 0.2), ("word1", B(4) + 0.35), ("word2", B(5) + 0.35), ("word3", B(6) + 0.4), ("shape1", B(8)), ("shape2", B(10)), ("shape3", B(12)),
            ("ease", B(15.5)), ("field", B(19.4)), ("blink1", B(22)), ("blink2", B(24)), ("w1", B(25) + 0.4), ("w2", B(26) + 0.4), ("w3", B(28)), ("sign", timing["total"] - 0.25)]


def texts(content: Content) -> list[str]:
    return [t for t in [content.brand, content.tagline, *content.opener, *content.shapes, content.claim_1, content.claim_2, *content.blink, *content.words] if t]
