"""Finding every independent piece of content in a long video: understand it as a whole first, then pick, check and trim.

Steps (each is a real model call over the real transcript, validated, never invented):

  enhance   repair obvious speech-recognition errors per segment; the raw text and its timing are never replaced
  outline   a topic map of the whole video (windows, then one merge), so a later window is judged with global context
  find      candidates from each window, each with exact segment ranges (several ranges allowed: hook + explanation)
  validate  a second look with the preceding context and the global outline: standalone? natural start and end? faithful hook?
  snap      boundaries from real word times (never mid-word or mid-sentence), de-duplication by time overlap and by meaning

The number of candidates is whatever the video really holds: nothing here pads a list to a target.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import llm

log = logging.getLogger(__name__)
WINDOW_S = 420.0              # transcript shown to the model per window
WINDOW_OVERLAP_S = 45.0
ENHANCE_BATCH = 14            # segments per enhancement call: small, so one provider error costs little and a retry is cheap
OUTLINE_ROUTE, FINDER_ROUTE, VALIDATOR_ROUTE = "long_video_outline", "long_video_clip_finder", "long_video_clip_validator"
ENHANCE_ROUTES = ("long_video_enhance", "creative_revision")     # the light model first, a steadier one when it fails
MIN_CLIP_S, MAX_CLIP_S = 10.0, 150.0
CATEGORIES = ("آموزشی", "داستان", "انگیزشی", "نکتهٔ کاربردی", "دیدگاه تند", "مثال و تجربه", "پرسش و پاسخ", "طنز", "تحلیل", "سایر")
FILLERS = ("خب", "خوب", "ببینید", "ببین", "یعنی", "حالا", "بله", "آره", "می‌گم", "میگم")


class _M(BaseModel):
    model_config = ConfigDict(extra="ignore")


def _t(value, limit=400) -> str:
    return " ".join(str(value or "").split())[:limit]


# ── enhance ─────────────────────────────────────────────────────────────────────────────────────────

class EnhancedItem(_M):
    id: str
    text: str = ""
    uncertain: list[str] = Field(default_factory=list)

    @field_validator("text", mode="before")
    @classmethod
    def _text(cls, value):
        return _t(value, 1200)

    @field_validator("uncertain", mode="before")
    @classmethod
    def _unc(cls, value):
        return [_t(v, 80) for v in (value or []) if _t(v, 80)][:6] if isinstance(value, list) else []


class EnhancedBatch(_M):
    items: list[EnhancedItem] = Field(default_factory=list)


ENHANCE = """You repair a Persian (and sometimes English) speech-to-text transcript, segment by segment. The speaker's words and
meaning are sacred: fix only what is clearly an ASR mistake or a typographic problem.

Do: correct obviously misheard words using the neighbouring lines; fix proper names and technical terms the context makes certain;
use Persian orthography (ی ک, half-space ‌ in می‌شود / کتاب‌ها), add Persian punctuation (، ؟ .); keep English terms as spoken.
Do not: summarise, translate, reorder, merge or split segments, add words the speaker did not say, soften opinions, or "improve" style.
If you are not sure, keep the original words and list the doubtful phrase in `uncertain`.

Return ONLY JSON {"items": [{"id": "<same id>", "text": "<corrected text>", "uncertain": ["<doubtful phrase>"]}]} with EVERY input id."""


def tokens(text: str) -> list[str]:
    return re.findall(r"[\w؀-ۿ]+", _plain(text))


def _plain(text: str) -> str:
    return str(text).replace("ي", "ی").replace("ك", "ک").replace("‌", "").lower()


def overlap(a: str, b: str) -> float:
    left, right = tokens(a), tokens(b)
    if not left or not right:
        return 0.0
    common = len(set(left) & set(right))
    return common / max(len(set(left)), len(set(right)))


def accept_enhancement(raw: str, enhanced: str) -> bool:
    """A correction may fix words, not change the content: similar vocabulary and similar length, or it is rejected."""
    if not enhanced.strip():
        return False
    ratio = len(enhanced) / max(1, len(raw))
    if not 0.6 <= ratio <= 1.5:
        return False
    # Speech-recognition fixes change spellings (many words differ) while the letters stay close; a rewrite changes both.
    import difflib
    similar = difflib.SequenceMatcher(None, _plain(raw), _plain(enhanced), autojunk=False).ratio()
    return overlap(raw, enhanced) >= 0.55 or similar >= 0.72


def enhance_segments(segments: list[dict], context: list[dict] | None = None, ask: Optional[Callable] = None, deadline: Optional[float] = None) -> list[dict]:
    """Add ``enhanced_text`` / ``flags`` to each segment (in place semantics: returns new dicts). Raw text is kept untouched."""
    ask = ask or llm.ask
    out = []
    for start in range(0, len(segments), ENHANCE_BATCH):
        batch = segments[start:start + ENHANCE_BATCH]
        if deadline is not None and time.monotonic() > deadline:       # out of time: the rest keeps its raw words, marked as such
            by_id = {}
            for seg in batch:
                out.append({**seg, "enhanced_text": seg["text"], "flags": ["not_enhanced"], "uncertain": [], "changed": False})
            continue
        before = (context or [])[-3:] if start == 0 else out[-3:]
        request = llm.dumps({"previous_lines": [s.get("enhanced_text") or s["text"] for s in before],
                             "segments": [{"id": s["id"], "text": s["text"]} for s in batch]})
        by_id = {}
        for route in ENHANCE_ROUTES:
            try:
                result = ask(EnhancedBatch, ENHANCE, request, route=route, tokens=5000, attempts=2)
                by_id = {item.id: item for item in result.items}
                break
            except Exception as exc:
                log.warning("transcript enhancement on %s failed for a batch: %s", route, exc)
        for seg in batch:
            item = by_id.get(seg["id"])
            enhanced, flags = seg["text"], []
            if item is None:
                flags.append("not_enhanced")
            elif accept_enhancement(seg["text"], item.text):
                enhanced = item.text
                flags.extend(["uncertain"] if item.uncertain else [])
            else:
                flags.append("rejected_change")                # the model rewrote too much: keep the raw words (its attempt is kept for review)
            out.append({**seg, "enhanced_text": enhanced, "flags": flags,
                        "uncertain": (item.uncertain if item else []), "changed": enhanced != seg["text"],
                        **({"proposed": item.text} if "rejected_change" in flags and item else {})})
    return out


# ── outline ─────────────────────────────────────────────────────────────────────────────────────────

class Topic(_M):
    title: str
    summary: str = ""
    start: float = 0
    end: float = 0
    key_points: list[str] = Field(default_factory=list)

    @field_validator("title", "summary", mode="before")
    @classmethod
    def _c(cls, value):
        return _t(value, 300)

    @field_validator("key_points", mode="before")
    @classmethod
    def _k(cls, value):
        return [_t(v, 200) for v in (value or [])][:6] if isinstance(value, list) else []


class WindowTopics(_M):
    topics: list[Topic] = Field(default_factory=list)


class Outline(_M):
    overview: str = ""
    kind: str = ""                 # podcast | lecture | interview | monologue | tutorial ...
    speakers: str = ""
    terms: list[str] = Field(default_factory=list)       # names and terms to spell consistently
    topics: list[Topic] = Field(default_factory=list)

    @field_validator("overview", "kind", "speakers", mode="before")
    @classmethod
    def _c(cls, value):
        return _t(value, 700)

    @field_validator("terms", mode="before")
    @classmethod
    def _terms(cls, value):
        return [_t(v, 60) for v in (value or [])][:40] if isinstance(value, list) else []


OUTLINE_WINDOW = """You map the structure of a long video from one window of its transcript. Lines look like "[mm:ss] text".
Return ONLY JSON {"topics": [{"title": "<specific Persian topic title>", "summary": "<2 sentences: what is actually said>",
"start": <seconds>, "end": <seconds>, "key_points": ["<claim, example, story or advice stated here>"]}]}.
Be specific to what is said (names, numbers, examples). Topics follow the speech in order and do not overlap."""

OUTLINE_MERGE = """You receive topic maps of consecutive windows of one long video. Merge them into one outline: join topics that continue
across a window edge, keep real topic changes, and describe the whole video. Return ONLY JSON
{"overview": "<3-4 sentences: what this video is, who speaks, what it is for>", "kind": "<podcast|lecture|interview|monologue|tutorial|other>",
"speakers": "<who speaks, as far as the text shows>", "terms": ["<proper names / technical terms spelled consistently>"],
"topics": [{"title": "...", "summary": "...", "start": 0, "end": 0, "key_points": ["..."]}]}."""


def clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else f"{seconds // 60:02d}:{seconds % 60:02d}"


def windows(segments: list[dict], size: float = WINDOW_S, overlap_s: float = WINDOW_OVERLAP_S) -> list[list[dict]]:
    out, cursor = [], 0
    while cursor < len(segments):
        end = cursor
        while end < len(segments) and segments[end]["end"] - segments[cursor]["start"] <= size:
            end += 1
        end = max(end, cursor + 1)
        out.append(segments[cursor:end])
        if end >= len(segments):
            break
        back = end
        while back > cursor + 1 and segments[end - 1]["end"] - segments[back - 1]["start"] < overlap_s:
            back -= 1
        cursor = max(back - 1, cursor + 1) if back < end else end
    return out


def text_of(seg: dict) -> str:
    return seg.get("enhanced_text") or seg["text"]


def render_window(window: list[dict], first_index: dict[str, int]) -> str:
    return "\n".join(f"S{first_index[s['id']]} [{clock(s['start'])}] {text_of(s)}" for s in window)


def build_outline(segments: list[dict], ask: Optional[Callable] = None, on_progress: Optional[Callable] = None) -> Outline:
    ask = ask or llm.ask
    index = {s["id"]: i for i, s in enumerate(segments)}
    maps = []
    for number, window in enumerate(windows(segments)):
        body = "\n".join(f"[{clock(s['start'])}] {text_of(s)}" for s in window)
        try:
            maps.append(ask(WindowTopics, OUTLINE_WINDOW, body, route=OUTLINE_ROUTE, tokens=3500, attempts=3).topics)
        except Exception as exc:
            log.warning("outline window failed: %s", exc)
            maps.append([Topic(title="بخش بدون تحلیل", start=window[0]["start"], end=window[-1]["end"])])
        if on_progress:
            on_progress(number + 1)
    flat = [t.model_dump() for window_topics in maps for t in window_topics]
    if len(maps) == 1:
        merged = Outline(overview=flat[0]["summary"] if flat else "", topics=[Topic(**t) for t in flat])
        return merged
    try:
        return ask(Outline, OUTLINE_MERGE, llm.dumps({"windows": [[t.model_dump() for t in m] for m in maps],
                                                      "duration_s": segments[-1]["end"]}), route=OUTLINE_ROUTE, tokens=6000, attempts=3)
    except Exception as exc:
        log.warning("outline merge failed, concatenating windows: %s", exc)
        return Outline(topics=[Topic(**t) for t in flat])


# ── find ────────────────────────────────────────────────────────────────────────────────────────────

class Span(_M):
    start_seg: int = Field(alias="from", ge=0)
    end_seg: int = Field(alias="to", ge=0)
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @field_validator("start_seg", "end_seg", mode="before")
    @classmethod
    def _id(cls, value):
        return int(re.sub(r"\D", "", str(value)) or 0)


class RawCandidate(_M):
    title: str
    summary: str = ""
    hook: str = ""
    hook_source: str = "written"          # "quote": taken from the speech, "written": rewritten by the model
    category: str = "سایر"
    ranges: list[Span] = Field(default_factory=list)
    rationale: str = ""
    scores: dict[str, float] = Field(default_factory=dict)
    needs_context: bool = False

    @field_validator("title", "summary", "hook", "rationale", mode="before")
    @classmethod
    def _c(cls, value):
        return _t(value, 500)

    @field_validator("scores", mode="before")
    @classmethod
    def _s(cls, value):
        out = {}
        for k, v in (value or {}).items() if isinstance(value, dict) else []:
            try:
                out[str(k)[:30]] = max(0.0, min(10.0, float(v)))
            except (TypeError, ValueError):
                pass
        return out

    @field_validator("category", mode="before")
    @classmethod
    def _cat(cls, value):
        return value if value in CATEGORIES else "سایر"


class CandidateBatch(_M):
    candidates: list[RawCandidate] = Field(default_factory=list)


FIND = f"""You are a senior short-form editor and content strategist reading ONE window of a long video's transcript, with the
whole video's outline for context. Find every piece that could stand alone as a short video (reel / short clip) - and only those.

A candidate must: make sense without the rest of the video; open on something that earns attention (a claim, a tension, a number,
a question, a story beat); carry real value (teaches, moves, surprises, advises, entertains); end naturally; be {MIN_CLIP_S:g}-{MAX_CLIP_S:g}
seconds of speech (usually 25-90). It may be built from SEVERAL ranges (for example the best hook line from later + the explanation).
HOW MANY: the person wants as many publishable pieces as the video really holds. A spoken talk like this usually holds one usable piece every
2-3 minutes, so a window of about 7 minutes should normally give 2-5 candidates. Do not stop at the first good one: go through the whole window
and list every distinct idea, story, example, analogy, piece of advice, strong claim, list or question-and-answer that stands alone, from the
strongest down to a pieces you would honestly score 6 or more. Short quotable pieces (10-30 seconds) count. Return an empty list only when
the window is truly empty of value (greetings, logistics, housekeeping). Never pad with weak pieces, and never return two candidates about the
same idea (different angles of one idea are ONE candidate). If a line only makes sense after earlier context, add the context line to the range
(or mark needs_context true).

Lines look like "S12 [mm:ss] text". Return ONLY JSON {{"candidates": [{{
 "title": "<specific Persian title, not generic>", "summary": "<what the viewer gets, 1-2 sentences>",
 "hook": "<the opening line: prefer a verbatim quote from the speech; else write one faithful to it>", "hook_source": "quote|written",
 "category": "<one of: {' / '.join(CATEGORIES)}>", "ranges": [{{"from": "S12", "to": "S19"}}],
 "rationale": "<why this works, citing what is said>", "needs_context": false,
 "scores": {{"hook": 0, "standalone": 0, "value": 0, "emotion": 0, "viral": 0, "editing": 0}} }}]}}
Scores are 0-10 and must be honest (most good clips are 6-8). Use only segment ids that appear in the window."""


def find_in_window(window: list[dict], index: dict[str, int], outline: Outline, ask: Optional[Callable] = None, focus: str = "") -> list[RawCandidate]:
    ask = ask or llm.ask
    request = (f"WHOLE-VIDEO OUTLINE\n{llm.dumps(outline.model_dump(exclude={'topics'}))}\nTopics: "
               + "; ".join(f"[{clock(t.start)}] {t.title}" for t in outline.topics)[:2500]
               + f"\n\nWINDOW {clock(window[0]['start'])}-{clock(window[-1]['end'])}\n{render_window(window, index)}")
    if focus:
        request = f"THE USER ASKED SPECIFICALLY FOR: {focus}\nOnly offer clips that fit this request.\n\n" + request
    return ask(CandidateBatch, FIND, request, route=FINDER_ROUTE, tokens=7000, attempts=3).candidates


# ── validate ────────────────────────────────────────────────────────────────────────────────────────

class Verdict(_M):
    index: int
    keep: bool = True
    standalone: float = 0
    title: str = ""
    hook: str = ""
    summary: str = ""
    category: str = ""
    reason: str = ""
    trim_from: Optional[int] = None         # a better first segment inside the candidate
    trim_to: Optional[int] = None           # a better last segment inside the candidate
    context_from: Optional[int] = None      # earlier segment to add so the clip is understandable
    problems: list[str] = Field(default_factory=list)

    @field_validator("title", "hook", "summary", "reason", mode="before")
    @classmethod
    def _c(cls, value):
        return _t(value, 500)

    @field_validator("trim_from", "trim_to", "context_from", mode="before")
    @classmethod
    def _n(cls, value):
        digits = re.sub(r"\D", "", str(value or ""))
        return int(digits) if digits else None

    @field_validator("problems", mode="before")
    @classmethod
    def _p(cls, value):
        return [_t(v, 200) for v in (value or [])][:5] if isinstance(value, list) else []


class VerdictBatch(_M):
    verdicts: list[Verdict] = Field(default_factory=list)


VALIDATE = """You are the final editor checking candidate clips against the whole video. For each candidate you get its transcript, the 60
seconds BEFORE it and the outline. Decide:
- keep: is it genuinely standalone and valuable? Drop vague, trivial, mid-thought, or context-dependent clips.
- standalone 0-10: would a stranger understand it with no other part of the video?
- starts/ends: if the opening has filler/throat-clearing or the end trails off, give trim_from / trim_to (segment numbers inside the candidate).
- context: if one earlier sentence fixes a missing reference, give context_from (a segment number from the "before" lines).
- hook: it must be faithful to what is said; rewrite it if it overclaims. Keep titles specific, no clickbait that the speech does not deliver.
Return ONLY JSON {"verdicts": [{"index": 0, "keep": true, "standalone": 0, "title": "", "hook": "", "summary": "", "category": "",
"reason": "<why keep or drop>", "trim_from": null, "trim_to": null, "context_from": null, "problems": []}]} with every input index."""


def validate_candidates(candidates: list[dict], segments: list[dict], outline: Outline, ask: Optional[Callable] = None) -> list[Verdict]:
    ask = ask or llm.ask
    verdicts: dict[int, Verdict] = {}
    for start in range(0, len(candidates), 6):
        batch = candidates[start:start + 6]
        payload = []
        for offset, cand in enumerate(batch):
            lo, hi = cand["seg_from"], cand["seg_to"]
            first_time = segments[lo]["start"]
            before = [s for s in segments[max(0, lo - 40):lo] if s["start"] >= first_time - 60]
            payload.append({"index": start + offset, "title": cand["title"], "hook": cand["hook"],
                            "before": [f"S{segments.index(s)} {text_of(s)}" for s in before][-10:],
                            "transcript": [f"S{i} {text_of(segments[i])}" for i in range(lo, hi + 1)][:60]})
        try:
            result = ask(VerdictBatch, VALIDATE, llm.dumps({"outline": outline.model_dump(exclude={'topics'}), "candidates": payload}),
                         route=VALIDATOR_ROUTE, tokens=5000, attempts=3)
            for verdict in result.verdicts:
                verdicts[verdict.index] = verdict
        except Exception as exc:
            log.warning("candidate validation unavailable: %s", exc)
    return [verdicts.get(i) or Verdict(index=i, keep=True, standalone=0, reason="بررسی مستقل در دسترس نبود") for i in range(len(candidates))]


# ── boundaries, duplicates, identity ────────────────────────────────────────────────────────────────

def snap_range(first: int, last: int, segments: list[dict], lead: float = 0.12, tail: float = 0.30) -> tuple[float, float]:
    """Seconds for a range of segments: the first word's start and the last word's end, never inside a word, never into the next one."""
    start = segments[first]["words"][0]["start"] if segments[first].get("words") else segments[first]["start"]
    end = segments[last]["words"][-1]["end"] if segments[last].get("words") else segments[last]["end"]
    previous_end = segments[first - 1]["end"] if first > 0 else 0.0
    next_start = segments[last + 1]["start"] if last + 1 < len(segments) else end + tail
    return round(max(previous_end + 0.02, start - lead, 0.0), 2), round(min(end + tail, next_start - 0.02) if next_start > end else end, 2)


def trim_filler(first: int, last: int, segments: list[dict]) -> int:
    """Skip a leading segment that is only filler words ("خب", "ببینید") when a real sentence follows."""
    while first < last and len(tokens(text_of(segments[first]))) <= 2 and all(w in FILLERS for w in tokens(text_of(segments[first]))):
        first += 1
    return first


def total_seconds(ranges: list[tuple[float, float]]) -> float:
    return round(sum(b - a for a, b in ranges), 2)


def candidate_id(analysis_id: str, first_start: float) -> str:
    return "c" + hashlib.sha1(f"{analysis_id}:{round(first_start / 4)}".encode()).hexdigest()[:9]


def same_content(a: dict, b: dict) -> bool:
    """Two candidates are one idea if their times overlap a lot, or their titles and summaries say the same thing."""
    def covered(x, y):
        inter = 0.0
        for s1, e1 in x["ranges"]:
            for s2, e2 in y["ranges"]:
                inter += max(0.0, min(e1, e2) - max(s1, s2))
        return inter / max(1.0, min(total_seconds([tuple(r) for r in x["ranges"]]), total_seconds([tuple(r) for r in y["ranges"]])))
    if covered(a, b) >= 0.5:
        return True
    return overlap(a["title"] + " " + a["summary"], b["title"] + " " + b["summary"]) >= 0.62 and abs(a["ranges"][0][0] - b["ranges"][0][0]) < 600


def score_of(raw: RawCandidate, verdict: Verdict) -> float:
    base = sum(raw.scores.values()) / len(raw.scores) if raw.scores else 5.0
    return round((base * 0.6 + (verdict.standalone or base) * 0.4), 1)
