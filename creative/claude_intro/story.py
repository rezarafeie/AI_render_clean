"""Intro engine 1 — Story: a typographic little tale with a character (1080x1920, 30 fps, music and effects, no narrator). Template: kit/src/Story.tsx."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

KIND, WIDTH, HEIGHT, FPS, MUSIC, MUSIC_GAIN, FADE = "story", 1080, 1920, 30, "story", 0.45, 2.5
VISUALS = ("read", "think", "build", "multiply", "list", "counter")
STEP_SECONDS = {"read": 6.0, "think": 5.8, "build": 6.4, "multiply": 5.2, "list": 5.6, "counter": 5.2}


class Step(BaseModel):
    model_config = ConfigDict(extra="ignore")
    n: str = ""                       # «یک.»
    a: str = ""                       # first part of the headline («اول،»)
    b: str = ""                       # the verb, arrives grey and tilted then turns black («می‌بینم.»)
    sub: str = ""                     # one grey line under it
    visual: Literal["read", "think", "build", "multiply", "list", "counter"] = "read"
    cards: list[str] = Field(default_factory=list)      # read: three card titles
    status: str = ""                                    # read: «در حال دیدن…»
    units: list[str] = Field(default_factory=list)      # read: what the two counters count («کلمه», «ثانیه»)
    labels: list[str] = Field(default_factory=list)     # think: six storyboard card labels
    tracks: list[str] = Field(default_factory=list)     # build: four track names
    window: list[str] = Field(default_factory=list)     # build: the window's two titles (while filling, while finishing)
    command: str = ""                                   # build: a Latin command line («$ render --final»)
    unit: str = ""                                      # build: what is counted («فریم»)
    count: int = 100                                    # build: counted up to
    done: str = ""                                      # build: «✓ آماده · …»
    done_note: str = ""
    names: list[str] = Field(default_factory=list)      # multiply: up to six names, one per copy of the character
    items: list[str] = Field(default_factory=list)      # list: three or four rows ticked one by one
    value: float = 0                                    # counter: the number
    caption: str = ""                                   # counter: a small line under the unit


class Content(BaseModel):
    model_config = ConfigDict(extra="ignore")
    questions: list[str] = Field(default_factory=list)
    brand: str = ""
    syllables: str = ""               # «اِ · دی · تور · جی · پی · تی»
    pos: str = "اسم"
    prompt: str = ""                  # typed in the terminal: «خودت رو معرفی کن»
    once: str = ""                    # the handwritten line: «روزی روزگاری، یک پیام…»
    definition: list[str] = Field(default_factory=list)       # three short lines, a dictionary definition of the product
    badge: str = ""
    hello: str = "سلام."
    steps: list[Step] = Field(default_factory=list)
    hi: str = "سلام، من"
    moral_label: str = "نتیجهٔ قصه"
    moral: list[str] = Field(default_factory=list)            # two lines
    url: str = ""
    facts: list[dict] = Field(default_factory=list)           # [{"claim", "source"}] every capability the film names
    mascot_shape: str = "circle"
    accent: str = ""


EXAMPLE = {
    "brand": "ادیتور جی‌پی‌تی", "syllables": "اِ · دی · تور · جی · پی · تی", "pos": "اسم", "prompt": "خودت رو معرفی کن", "once": "روزی روزگاری، یک پیام…",
    "definition": ["تدوینگری که با حرف‌زدن", "کار می‌کند؛ از یک پیام", "تا ویدیوی آماده."], "badge": "✓ ۴۷ ثانیه", "hello": "سلام.",
    "steps": [
        {"n": "یک.", "a": "اول،", "b": "می‌بینم.", "sub": "ویدیو، عکس، لینک محصول؛ هر چه بدهی", "visual": "read", "cards": ["ویدیو.mp4", "رونوشت", "محصول.jpg"],
         "status": "در حال دیدن…", "units": ["کلمه", "ثانیه"]},
        {"n": "دو.", "a": "بعد،", "b": "فکر می‌کنم.", "sub": "قلاب، برش‌ها، استوری‌بورد؛ قبل از هر رندر", "visual": "think",
         "labels": ["قلاب", "معرفی", "نکته", "مثال", "جمع‌بندی", "دعوت"]},
        {"n": "سه.", "a": "بعد،", "b": "می‌سازم.", "sub": "کپشن، موشن، رنگ و صدا؛ تا خروجی نهایی", "visual": "build", "tracks": ["ویدیو", "کپشن", "موشن", "صدا"],
         "window": ["تایم‌لاین", "رندر"], "command": "$ render --final", "unit": "فریم", "count": 1410, "done": "✓ آماده · ۱۰۸۰×۱۹۲۰",
         "done_note": "صدا تراز شد · کپشن‌ها روی کلمه · خروجی پریمیر"},
        {"n": "چهار.", "a": "و چند نفر", "b": "می‌شوم.", "sub": "هر کار، موتور خودش را دارد", "visual": "multiply",
         "names": ["تدوین", "موشن‌گرافیک", "اکسپلینر", "دوبله", "کلیپ‌یاب", "اینستاگرام"]},
    ],
    "hi": "سلام، من", "moral_label": "نتیجهٔ قصه", "moral": ["همه‌چیز با یک پیام", "شروع می‌شود."], "url": "editor.rafiei.co", "mascot_shape": "spark",
    "facts": [{"claim": "ویدیو، عکس و لینک محصول را می‌گیرد", "source": "README"}],
}

GUIDE = """THE STORY INTRO (vertical 1080x1920, about 45 s, music only): the product introduces itself like a little tale. A terminal types a request to the
product, a small character made of the brand's own mark drops in, the brand's name is written, a dictionary entry defines it, then 3 or 4 STEPS
(«اول، می‌بینم.» «بعد، فکر می‌کنم.» ...) each with one drawn visual, then «سلام، من <brand>.» and a two-line moral.
Fill this JSON (Persian, written register for the headlines, short):
- brand: the product's name as it is written. syllables: its pronunciation split with « · ». pos: its part of speech («اسم»).
- prompt: what a person would type to the product to make it introduce itself (max 22 characters, colloquial).
- once: a handwritten opening line in the tale's voice (max 26 characters) ending with «…».
- definition: exactly 3 lines of at most 22 characters each: one sentence defining the product, broken in three.
- badge: a tiny fact with a check mark (max 14 characters) or "".
- steps: 3 or 4. Each: n («یک.» «دو.» ...), a (2-9 characters, ends with «،» when it is «اول،/بعد،»), b (one verb in first person, max 12 characters, ends
  with «.»), sub (max 40 characters: what exactly, three things separated by «،» then «؛» and a few words), visual and that visual's own fields:
    read     = cards pass under a scan line: cards (3 titles, each max 12 characters: what the product takes in), status (max 14), units (two nouns it counts).
    think    = scattered dots become a tree, one path lights up, six cards appear: labels (6 words, max 9 characters each: the parts of what it plans).
    build    = a dark window: four tracks fill, then a progress bar counts to done: tracks (4 words, max 7 characters), window (2 titles), command (Latin,
               max 18 characters), unit (one word), count (the number it counts to), done (max 22 characters starting with ✓), done_note (max 44).
    multiply = copies of the character jump to their places, each with a name: names (4 to 6, max 12 characters each: the product's parts or uses).
    list     = three or four rows are ticked: items (3-4, max 20 characters each).
    counter  = one big number counts up: value (a number from the FACTS), unit (max 14), caption (max 30).
  Use each visual at most once; the steps tell how the product works, in order.
- hi («سلام، من»), moral_label, moral: exactly 2 lines of at most 18 characters each: the one idea to remember. url: the product's address without https://.
- mascot_shape: the simple shape closest to the brand's OWN mark: spark (four-point star) | circle | square | drop | hex | diamond | cloud. Never another brand's mark.
- accent: the brand's accent colour as #rrggbb when the FACTS show one, else "".
- facts: every capability, number or claim the film shows, each with the source it came from."""


def plan(content: Content) -> tuple[dict, list[dict], float]:
    """(timing for the template, sound events, total seconds)."""
    once = 4.6
    dict_ = once + 4.8
    cursor = dict_ + 5.8
    starts = []
    for step in content.steps:
        starts.append(round(cursor, 3))
        cursor += STEP_SECONDS.get(step.visual, 5.6)
    hi = round(cursor, 3)
    moral = round(hi + 4.6, 3)
    total = round(moral + 3.8, 3)
    T = {"term": 0, "once": once, "dict": dict_, "steps": starts, "hi": hi, "moral": moral, "total": total}
    ev: list[dict] = []

    def e(t: float, k: str, g: float = 0.6) -> None:
        ev.append({"t": round(t, 3), "k": k, "g": g})

    per = min(0.13, (once - 2.5) / max(1, len(content.prompt)))
    for i in range(min(len(content.prompt), 18)):
        e(0.55 + i * per, "key", 0.5)
    e(once - 1.6, "drop", 0.7); e(once - 0.3, "whoosh", 0.6); e(once + 1.3, "swell", 0.5); e(dict_, "whoosh", 0.5); e(dict_ + 4.2, "pop", 0.6)
    for step, t in zip(content.steps, starts):
        e(t - 0.25, "whoosh", 0.5); e(t + 0.2, "tick", 0.6)
        if step.visual == "read":
            e(t + 1.2, "scan", 0.5)
        elif step.visual == "think":
            e(t + 2.9, "pop", 0.6)
        elif step.visual in {"build", "counter"}:
            e(t + 3.9, "ding", 0.6)
        elif step.visual == "multiply":
            for i in range(min(6, len(step.names))):
                e(t + 1.2 + i * 0.22, "pop", 0.5)
        elif step.visual == "list":
            for i in range(min(4, len(step.items))):
                e(t + 1.9 + i * 0.55, "tick", 0.6)
    e(hi - 0.2, "whoosh", 0.5); e(hi + 1.5, "ding", 0.5); e(moral, "swell", 0.6)
    return {"T": T, "total": total}, ev, total


def still_times(timing: dict) -> list[tuple[str, float]]:
    T = timing["T"]
    out = [("terminal", 2.6), ("name", T["once"] + 3.0), ("dictionary", T["dict"] + 4.6)]
    for i, t in enumerate(T["steps"]):
        out += [(f"step{i + 1}a", t + 2.4), (f"step{i + 1}b", t + 4.9)]
    out += [("hello", T["hi"] + 2.6), ("moral", T["moral"] + 3.0)]
    return out


def texts(content: Content) -> list[str]:
    out = [content.prompt, content.once, content.brand, *content.definition, *content.moral]
    for s in content.steps:
        out += [s.a, s.b, s.sub, *s.cards, *s.labels, *s.tracks, *s.names, *s.items, s.done, s.done_note, s.caption]
    return [t for t in out if t]
