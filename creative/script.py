"""Professional scriptwriting: write → measure → independent critic → bounded rewrite → executable beats.

This replaces the single "expand the concept into beats" call for videos that have no speech of their own (idea, product,
images). Narration used to be one field of one model call, checked only by a word-count rule. Now:

  write     a dedicated call writes the Persian script *and* what is seen under every line (visual-first)
  measure   real checks: speech seconds (``speech``), repeated phrases, clichés, lines without a picture
  critic    a separate model scores 13 criteria, each with a quote from the script as evidence; evidence that is not
            in the script is rejected and the score capped, so the numbers cannot be decorative
  rewrite   bounded (depth-dependent); the critic may ask for a different angle, structure, hook or ending, and a rewrite
            that only swaps synonyms is rejected

Quality is the same in Fast and Premium: depth only changes how many rewrite rounds the critic may ask for.
"""
from __future__ import annotations

import logging
import re
import time

from . import llm, speech
from .schemas import (CRITERIA, STRUCTURES, Beat, Concept, ContentBrief, CreativeUnavailable, CriterionScore, ReferenceProfile,
                      ScriptDraft, ScriptReport, ScriptReview)

WRITER_ROUTE, CRITIC_ROUTE = "script_writer", "script_critic"
log = logging.getLogger(__name__)

DEPTH_REWRITES = {"fast": 3, "premium": 5}
DECISIVE = ("hook_strength", "payoff_quality")
PATIENCE = 2           # rounds without a better score after which the loop stops: more rewriting is not helping
MAX_LINES = 8
MIN_LINES = 3
CLICHES = ("در دنیای امروز", "آیا می‌دانستید", "آیا میدونستید", "انقلاب", "با ما همراه باشید", "فراموش نکنید", "بی‌نظیر", "فوق‌العاده",
           "بهترین راه", "تا پایان ویدیو", "لایک و فالو", "نظر یادتون نره", "قدرت واقعی", "دنیای جدید", "آینده در دستان شما")
GENERIC_VISUALS = ("تصویر مرتبط", "تصویر زیبا", "پس‌زمینه", "ویدیوی مرتبط", "تصویری از", "عکس مرتبط", "stock", "نمای کلی")

WRITER = """You are an award-winning Persian short-form scriptwriter AND the video's creative director. You write the final spoken
script and, under every line, exactly what the viewer sees. The script is for a text-to-speech narrator: write the way people
speak Persian (natural, modern, polite colloquial unless the brief asks for formal), not the way an essay or an ad is written.

Craft rules
- Open with the hook in the first line: a specific tension, contradiction, number, or question about THIS topic. No warm-up.
- Keep a curiosity gap open: never answer the hook's question in the same line; the reveal comes at the turn.
- Make the ending echo the opening image or line so the video feels designed, and say who the last line is for.
- One idea per line. Short sentences. Concrete nouns and verbs; name the thing instead of the category.
- Use the chosen structure; let the turn (reframe/reveal) land late and the payoff be the last line, never a summary of earlier lines.
- Never write: filler, textbook definitions, empty slogans, advertising clichés, invented facts or numbers, a closing line that
  merely repeats the title. Do not add a sales call to action to education, a story or an opinion.
- Every spoken line is a complete, natural sentence that makes sense on its own and carries its own idea. Never a fragment that only continues the previous
  line (for example "برای تا دو ساعت موسیقی."): the sentence is finished within its own line, then the next line starts a new thought.
- For a product or an offer, SELL what it has: the strongest real benefits first (what the buyer gains in daily life, durability, the real numbers that matter
  such as battery hours, the price or offer), not trivia. Never give a scene to what the product lacks, to a limitation or to a disclaimer, and never say a feature
  is missing («ندارد»، «نیست»، «فاقد»): leave it out. Only when the brief itself asks to address it, do it in one honest clause inside a line.
- In a sales video the last line is the call to action: it names the offer or the next step (the price, where to buy, what to do now), not a vague "check it out".
- Each line must be a picture: say what is HEARD, what is SEEN (a concrete image or motion for THIS sentence, never generic
  decoration), WHY that picture, which element guides attention, and how this scene follows from the previous one.
- On-screen text (title) is 1-4 words that ADD to the narration (a number, a label, a contrast); it never repeats it.
- Respect the speech budget: it is measured in real spoken seconds, not words. Prefer fewer, stronger lines to rushed ones.
- If a reference style profile is given, carry its pacing, typography, motion language and composition into the scenes and name
  the trait each scene carries in reference_trait. Never copy the reference's own content or wording.
- If a verified asset catalog is given, a line that shows an asset must choose its index and match what the asset really shows.

Return ONLY JSON:
{"structure": "<one of the allowed structure ids>",
 "lines": [{"id": "L1", "role": "hook|tension|setup|claim|proof|reframe|turn|payoff|cta",
            "narration": "<exact spoken Persian>", "title": "<1-4 words on screen>",
            "hear": "<what the viewer should take from the words and feel>", "see": "<specific image or motion>",
            "why_visual": "<why this picture for this sentence>", "motion": "<how it moves, in renderer terms>",
            "emotion": "<feeling>", "focus": "<the element that leads the eye>", "link_prev": "<how it follows the previous scene>",
            "visual_type": "concept|stat|comparison|steps|ui_showcase|media_collage|chat|map_route|spec_callout|kinetic_type|before_after",
            "items": ["<up to four short verified labels>"], "source_asset_index": <index or null>,
            "reference_trait": "<trait carried, or empty>", "motion_engine": "default"}],
 "ending": "<the final image and the final line, in one sentence>",
 "visual_language": "<palette, typography and imagery rules kept through the video>",
 "pacing": "<where it speeds up and where it breathes>"}"""

CRITIC = """You are a hard-to-impress head of content and a native Persian editor. Judge the script below as it would perform in a
vertical short-form feed, using ONLY what is on the page. Score each criterion 0-10 (most work deserves 4-7) with a one-sentence
reason and EVIDENCE: an exact quote from the script (or a measured fact from `measured`) that justifies the score. A score without
real evidence will be discarded.

Criteria: hook_strength, originality, clarity, emotional_impact, audience_relevance, narrative_coherence, curiosity, memorability,
natural_persian (does it sound spoken, or like a translation / an ad?), visual_potential (does every line become a concrete picture?),
timing (use `measured` speech seconds against the budget), payoff_quality, reference_alignment (only when a reference profile
is given; otherwise score 10 with the reason "no reference").

In a sales video these are must_fix whatever the scores: a scene that is about a missing feature, a limitation or a disclaimer; a line that is a sentence fragment;
a closing line without a concrete offer or next step; weak trivia chosen over the product's strongest real benefits.

Then decide: verdict "ship" only if the hook and payoff are genuinely strong and no criterion is below 6; otherwise "rewrite".
For a rewrite, list must_fix (specific, actionable: name the line ids and what is wrong) and `change`, the structural moves
needed: angle | structure | hook | ending | cut | tone. If the angle itself is the problem, say so: synonyms will not fix it.

Write reason, must_fix and summary in Persian (evidence stays a verbatim quote). `measured` also lists soft `notes`: weigh them.

Return ONLY JSON:
{"scores": [{"criterion": "hook_strength", "score": 0, "reason": "...", "evidence": "<quote>"}],
 "verdict": "ship|rewrite", "must_fix": ["..."], "change": ["hook"], "summary": "<2 sentences in Persian>"}"""

REWRITE = """Rewrite the script. Keep what the critic did not criticise, fix every must_fix item, and make the structural changes the
critic asked for (a new angle, structure, hook or ending is allowed and expected when requested). Do not just substitute synonyms:
a rewrite that keeps the same sentences will be rejected. Obey every craft rule and the speech budget, and return the same JSON."""


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[\w؀-ۿ]+", text))


def similarity(a: str, b: str) -> float:
    left, right = _tokens(a), _tokens(b)
    return len(left & right) / len(left | right) if left | right else 1.0


def script_text(draft: ScriptDraft) -> str:
    return "\n".join(f"{line.id}: {line.narration}" for line in draft.lines)


def _plain(text: str) -> str:
    return re.sub(r"[\u200c\s]+", "", str(text).replace("ي", "ی").replace("ك", "ک"))


def measure(draft: ScriptDraft, duration_s: float, *, outro_s: float = 0.0, must_name: tuple | list = ()) -> dict:
    """Facts about the script that need no model: what the critic is shown, and what can force a rewrite regardless of scores."""
    narrations = [line.narration for line in draft.lines]
    seconds = [round(speech.speech_seconds(text), 2) for text in narrations]
    total, limit = sum(seconds), speech.budget(duration_s, outro_s=outro_s)
    problems: list[str] = []      # hard: force a rewrite whatever the critic says
    notes: list[str] = []         # soft: shown to the critic and reported, but not worth a rewrite round on their own
    if not MIN_LINES <= len(draft.lines) <= MAX_LINES:
        problems.append(f"تعداد صحنه‌ها {len(draft.lines)} است؛ باید بین {MIN_LINES} و {MAX_LINES} باشد.")
    if total > limit:
        problems.append(f"نریشن حدود {total:.1f} ثانیه طول می‌کشد و بیشتر از ظرفیت {limit:.1f} ثانیهٔ این ویدیو است.")
    elif total < limit * 0.45 and duration_s >= 12:
        problems.append(f"نریشن فقط حدود {total:.1f} ثانیه از {limit:.1f} ثانیهٔ ممکن را پر می‌کند؛ ویدیو خالی و کشدار می‌شود.")
    spoken = _plain(" ".join(narrations))
    spoken_words = {_plain(word) for word in re.split(r"[\s،؛.!؟?:؛\-]+", " ".join(narrations)) if _plain(word)}

    def heard(term: str) -> bool:
        """The whole phrase, or (for a multi-word term) at least a third of its words: «یاقوت تراش کله‌قندی» is heard as «یاقوت»."""
        if _plain(term) in spoken:
            return True
        words = [_plain(w) for w in re.split(r"[\s،؛.!؟?:\-]+", term) if len(_plain(w)) >= 3]
        return len(words) >= 2 and sum(w in spoken or w in spoken_words for w in words) * 3 >= len(words)

    missing = [term for term in must_name if _plain(term) and not heard(term)]
    if missing:
        problems.append("موضوع ویدیو در گفتار نیامده؛ این واژه‌ها باید شنیده شوند: " + "، ".join(f"«{t}»" for t in missing))
    opening = _plain(" ".join(narrations[:2]))
    if must_name and not any(_plain(term) in opening for term in must_name if _plain(term)) and not missing:
        notes.append("هیچ‌کدام از واژه‌های موضوع در دو جملهٔ اول نیامده؛ بیننده دیر می‌فهمد ویدیو دربارهٔ چیست.")
    found = sorted({phrase for phrase in CLICHES if phrase in " ".join(narrations)})
    if found:
        problems.append("عبارت‌های کلیشه‌ای: " + "، ".join(f"«{p}»" for p in found))
    for line, text in zip(draft.lines, narrations):
        if not text.strip():
            problems.append(f"{line.id}: متن نریشن خالی است.")
        if len(line.see.strip()) < 14 or (len(line.see.strip()) < 45 and any(generic in line.see for generic in GENERIC_VISUALS)):
            problems.append(f"{line.id}: تصویر مشخص و اجرایی ندارد («{line.see[:40]}»).")
        if line.title and _tokens(line.title) and _tokens(line.title) <= _tokens(text):
            notes.append(f"{line.id}: متن روی تصویر فقط تکرار نریشن است.")
    seen: dict[str, str] = {}
    for line in draft.lines:
        words = re.findall(r"[\w؀-ۿ]+", line.narration)
        for i in range(len(words) - 2):
            gram = " ".join(words[i:i + 3])
            if gram in seen and seen[gram] != line.id:
                notes.append(f"عبارت «{gram}» در {seen[gram]} و {line.id} تکرار شده است.")
                break
            seen.setdefault(gram, line.id)
    if draft.structure and draft.structure not in STRUCTURES:
        problems.append(f"ساختار «{draft.structure}» از فهرست مجاز نیست.")
    return {"line_seconds": dict(zip((line.id for line in draft.lines), seconds)), "total_speech_s": round(total, 2),
            "budget_s": round(limit, 2), "target_s": duration_s, "problems": problems, "notes": notes}


def _verify(review: ScriptReview, draft: ScriptDraft, measured: dict, has_reference: bool) -> ScriptReview:
    """A score only stands if its evidence is on the page: a quoted phrase from the script or a real measured number."""
    text = script_text(draft) + " " + " ".join(f"{line.title} {line.see} {line.hear} {line.why_visual} {line.motion} {line.emotion} {line.focus} {line.link_prev} "
                                              f"{' '.join(line.items)}" for line in draft.lines)
    squash = lambda value: re.sub(r"[\s\u200c\u200d\u200f\u200e.,،؛;:!?؟«»\"'“”‘’()\[\]…\-–—]+", "", value.replace("ي", "ی").replace("ك", "ک"))
    body = squash(text)

    def on_page(evidence: str) -> bool:
        """A quote counts if it, or each piece of it (the critic often joins several quotes with … | + /), is in the script."""
        whole = squash(evidence)
        if len(whole) >= 6 and whole in body:
            return True
        pieces = [squash(part) for part in re.split(r"\s*(?:…|\.\.\.|\||\+|/|؛|;|\n|[«»\"“”])\s*", evidence)]
        pieces = [part for part in pieces if len(part) >= 6]
        return bool(pieces) and all(part in body for part in pieces)

    seen: dict[str, CriterionScore] = {}
    for score in review.scores:
        if score.criterion not in CRITERIA or score.criterion in seen:
            continue
        quoted = on_page(score.evidence)
        measured_fact = score.criterion == "timing" and any(ch.isdigit() for ch in score.evidence)
        none_ok = score.criterion == "reference_alignment" and not has_reference
        if not (quoted or measured_fact or none_ok):
            score.verified = False
            if score.criterion in DECISIVE:                       # the hook and the payoff decide a ship: their proof must be on the page
                score.score = min(score.score, 5.0)
            # any other criterion keeps its score: the critic described the line instead of quoting it, which is no reason to fail a script it approved
        seen[score.criterion] = score
    for criterion in CRITERIA:                                   # a criterion the critic skipped is not a pass
        if criterion not in seen:
            seen[criterion] = CriterionScore(criterion=criterion, score=0 if has_reference or criterion != "reference_alignment" else 10,
                                             reason="بررسی نشد." if (has_reference or criterion != "reference_alignment") else "رفرنسی وجود ندارد.",
                                             verified=criterion == "reference_alignment" and not has_reference)
    review.scores = [seen[c] for c in CRITERIA]
    if measured["problems"]:
        review.verdict = "rewrite"
        review.must_fix = measured["problems"] + review.must_fix
    weak = [s for s in review.scores if s.score < 6]
    if review.verdict == "ship" and weak:      # a criterion without checkable evidence is capped below 6, so it cannot ship either
        review.verdict = "rewrite"
        review.must_fix = [f"{s.criterion}: {s.reason if s.verified else 'شاهد نقل‌شده در متن پیدا نشد'}" for s in weak] + review.must_fix
    return review


def reference_digest(reference: ReferenceProfile | None) -> str:
    if not reference or not reference.usable:
        return "No reference style (none was supplied or it could not be analysed). Do not claim to follow one."
    data = reference.model_dump(exclude={"status", "reason", "shot_lengths_s", "frames_used"})
    return "Reference style profile (observed in the reference video; reproduce the technique, not the content):\n" + llm.dumps(data)


def _context(brief: ContentBrief, concept: Concept, reference: ReferenceProfile | None, source: str, caps: str,
             duration_s: float, outro_s: float) -> str:
    limit = speech.budget(duration_s, outro_s=outro_s)
    return (f"{llm.dumps({'brief': brief.model_dump(exclude={'key_moments'}), 'concept': concept.model_dump(exclude={'beats'})})}\n\n"
            f"Allowed structures: {', '.join(STRUCTURES)}\n"
            f"Target length: {duration_s:g} s. SPEECH BUDGET: at most {limit:.1f} seconds of real Persian speech in total "
            f"(about {speech.max_letters(limit, pauses=MAX_LINES)} letters in all, punctuation pauses included). "
            f"Between {MIN_LINES} and {MAX_LINES} scenes.\n\n{reference_digest(reference)}\n\n"
            f"Source evidence:\n{source}\n\nCapabilities:\n{caps}")


def write(brief, concept, reference, source, caps, duration_s, *, outro_s=0.0, used=None) -> ScriptDraft:
    return llm.ask(ScriptDraft, WRITER, _context(brief, concept, reference, source, caps, duration_s, outro_s),
                   route=WRITER_ROUTE, tokens=5500, attempts=4, used=used)


CONVERGE = """This is a FOLLOW-UP review. `previous_must_fix` lists what you asked to change last time. Judge the new script on three things only:
(1) is each previous must_fix really fixed, (2) the measured facts (timing, subject words, scene count), (3) any criterion that is now below 6.
Do NOT raise new taste-based objections that you did not raise before: a script whose previous demands are met, whose measured facts
are fine and whose criteria are all at least 6 (hook_strength and payoff_quality at least 7) is "ship". Keep scoring honestly."""


def critique(draft: ScriptDraft, brief, concept, reference, measured, *, used=None, previous: ScriptReview | None = None) -> ScriptReview:
    request = llm.dumps({**({"previous_must_fix": previous.must_fix[:8], "previous_summary": previous.summary} if previous else {}),"brief": brief.model_dump(exclude={"key_moments"}), "concept": concept.model_dump(exclude={"beats"}),
                         "script": [line.model_dump() for line in draft.lines], "ending": draft.ending, "structure": draft.structure,
                         "measured": measured, "reference": reference.model_dump(exclude={"shot_lengths_s"}) if reference and reference.usable else None})
    raw = llm.ask(ScriptReview, CRITIC + ("\n\n" + CONVERGE if previous else ""), request, route=CRITIC_ROUTE, tokens=4500, used=used)
    return _verify(raw, draft, measured, bool(reference and reference.usable))


def rewrite(previous: ScriptDraft, review: ScriptReview, brief, concept, reference, source, caps, duration_s, measured, *,
            outro_s=0.0, used=None) -> ScriptDraft:
    request = (_context(brief, concept, reference, source, caps, duration_s, outro_s) +
               f"\n\nPrevious script:\n{llm.dumps(previous.model_dump())}\n\nCritic's must_fix:\n{llm.dumps(review.must_fix)}\n"
               f"Structural changes requested: {review.change or ['none']}\nMeasured: {llm.dumps({k: measured[k] for k in ('line_seconds', 'total_speech_s', 'budget_s')})}")
    return llm.ask(ScriptDraft, WRITER + "\n\n" + REWRITE, request, route=WRITER_ROUTE, tokens=5500, attempts=4, used=used)


def run(brief: ContentBrief, concept: Concept, caps: str, source: str, *, duration_s: float, reference: ReferenceProfile | None = None,
        depth: str = "fast", outro_s: float = 0.0, used: list[str] | None = None, started: float | None = None,
        budget_s: float = 240) -> tuple[ScriptDraft, ScriptReport]:
    """The bounded loop. At most ``1 + rewrites`` writer calls and ``1 + rewrites`` critic calls, whatever the scores say."""
    started = started or time.monotonic()
    rewrites = DEPTH_REWRITES.get(depth, 1)
    draft = write(brief, concept, reference, source, caps, duration_s, outro_s=outro_s, used=used)
    report = ScriptReport(structure=draft.structure)
    review: ScriptReview | None = None
    previous_review: ScriptReview | None = None
    best, stale = -1.0, 0
    for attempt in range(rewrites + 1):
        measured = measure(draft, duration_s, outro_s=outro_s, must_name=brief.must_name)
        try:
            review = critique(draft, brief, concept, reference, measured, used=used, previous=previous_review)
        except CreativeUnavailable as exc:
            log.warning("script critic unavailable: %s", exc)
            review = ScriptReview(verdict="rewrite", must_fix=measured["problems"] + ["بازبینی مستقل کیفیت انجام نشد؛ سناریو تأیید نشده است."],
                                  summary="منتقد در دسترس نبود؛ فقط بررسی‌های اندازه‌گیری‌شده انجام شد.")
            review.scores = []
        report.attempts = attempt + 1
        report.history.append({"attempt": attempt + 1, "verdict": review.verdict, "must_fix": review.must_fix[:6], "change": review.change,
                               "speech_s": measured["total_speech_s"], "structure": draft.structure})
        out_of_time = time.monotonic() - started > budget_s
        mean = sum(item.score for item in review.scores) / max(1, len(review.scores))
        best, stale = (mean, 0) if mean > best + 0.05 else (best, stale + 1)
        if review.verdict == "ship" or attempt == rewrites or out_of_time or stale >= PATIENCE:
            report.stopped = "shipped" if review.verdict == "ship" else "time" if out_of_time else "stalled" if stale >= PATIENCE else "cap"
            break
        previous_review = review
        try:
            candidate = rewrite(draft, review, brief, concept, reference, source, caps, duration_s, measured, outro_s=outro_s, used=used)
        except CreativeUnavailable as exc:
            log.warning("script rewrite unavailable: %s", exc)
            report.stopped = "unavailable"
            break
        asked = [item for item in review.must_fix if item not in measured["problems"]]       # what the critic itself wants changed
        if similarity(script_text(candidate), script_text(draft)) > 0.8 and (asked or review.change):
            report.history[-1]["rewrite_rejected"] = "فقط واژه‌ها جابه‌جا شده بود"
            continue
        draft = candidate
    final = measure(draft, duration_s, outro_s=outro_s, must_name=brief.must_name)
    # Fitting the video is not a matter of taste: if the script still overruns, tighten it (at most twice), then the result is reviewed once more.
    tightened = False
    for _ in range(2):
        if final["total_speech_s"] <= final["budget_s"] or time.monotonic() - started > budget_s * 1.25:
            break
        over = final["total_speech_s"] - final["budget_s"]
        order = sorted(final["line_seconds"].items(), key=lambda item: -item[1])[:3]
        ask = ScriptReview(verdict="rewrite", change=["cut"], must_fix=[
            f"نریشن {final['total_speech_s']:.1f} ثانیه است و باید حداکثر {final['budget_s']:.1f} ثانیه شود: {over + 0.3:.1f} ثانیه کم کن. "
            f"ایده، هوک و پایان را نگه دار و طولانی‌ترین خط‌ها را کوتاه کن ({', '.join(f'{k}: {v:.1f}s' for k, v in order)})."])
        try:
            tighter = rewrite(draft, ask, brief, concept, reference, source, caps, duration_s, final, outro_s=outro_s, used=used)
        except CreativeUnavailable as exc:
            log.warning("script tightening unavailable: %s", exc)
            break
        after = measure(tighter, duration_s, outro_s=outro_s, must_name=brief.must_name)
        report.history.append({"attempt": report.attempts, "tighten": True, "speech_s_before": final["total_speech_s"], "speech_s_after": after["total_speech_s"]})
        if after["total_speech_s"] < final["total_speech_s"]:
            draft, final = tighter, after
            tightened = True
    if tightened and review is not None and review.verdict != "ship" and time.monotonic() - started <= budget_s * 1.6:
        # The verdict was about the draft BEFORE it was tightened to fit: the draft that would ship must be judged itself.
        try:
            second = critique(draft, brief, concept, reference, final, used=used, previous=previous_review or review)
        except CreativeUnavailable as exc:
            log.warning("final script review unavailable: %s", exc)
        else:
            review = second
            report.history.append({"attempt": report.attempts + 1, "verdict": review.verdict, "must_fix": review.must_fix[:6], "change": review.change,
                                   "speech_s": final["total_speech_s"], "structure": draft.structure, "after_tightening": True})
    report.review = review
    report.structure = draft.structure
    report.speech_seconds = final["total_speech_s"]
    report.budget_seconds = final["budget_s"]
    report.timing_ok = final["total_speech_s"] <= final["budget_s"]
    report.deterministic = final["problems"] + final["notes"]
    report.hard_problems = list(final["problems"])
    return draft, report


def passes(report: ScriptReport) -> bool:
    """May this script become a video? The critic's own "ship", or: the measured facts are clean, every criterion is at least 6 with checkable
    evidence and the hook and the payoff at least 7. (The critic keeps finding new taste objections; the numbers are what is checkable.)"""
    review = report.review
    if review is None or not report.timing_ok or report.hard_problems:
        return False
    if review.verdict == "ship":
        return True
    by = {item.criterion: item for item in review.scores}
    if len(by) < len(CRITERIA) or any(not item.verified and item.criterion in DECISIVE for item in by.values()):
        return False
    return all(item.score >= 6 for item in by.values()) and by["hook_strength"].score >= 7 and by["payoff_quality"].score >= 7


def to_beats(draft: ScriptDraft, duration_s: float) -> list[Beat]:
    """The executable storyboard contract: each beat points at its script line and carries why it exists."""
    beats = []
    raw = [max(speech.speech_seconds(line.narration) + 0.35, 1.2) for line in draft.lines]
    mean = sum(raw) / len(raw) if raw else 1.0              # relative weights (mean 1): Beat accepts 0..10, seconds would overflow it
    for index, line in enumerate(draft.lines, 1):
        beats.append(Beat(
            role=line.role, intent=line.hear, visual=line.see, motion=line.motion, title=line.title, narration=line.narration,
            source_asset_index=line.source_asset_index, visual_type=line.visual_type, items=line.items,
            duration_weight=min(10.0, max(0.2, raw[index - 1] / mean)), motion_engine=line.motion_engine,
            line_id=line.id or f"L{index}", why_visual=line.why_visual, emotion=line.emotion, focus=line.focus,
            link_prev=line.link_prev, reference_trait=line.reference_trait))
    return beats


def refusal(report: ScriptReport) -> str:
    """The plain reasons a script was not accepted: what stopped the loop, the measured facts, the criteria below the bar, the critic's own requests."""
    parts = []
    review = report.review
    stopped = {"cap": "سقف دورهای بازنویسی تمام شد", "time": "زمان طراحی تمام شد", "stalled": "بازنویسی دیگر نمره را بهتر نکرد", "unavailable": "نویسنده در دسترس نبود"}.get(report.stopped)
    if stopped:
        parts.append(stopped)
    if not report.timing_ok:
        parts.append(f"نریشن {report.speech_seconds:.1f} ثانیه است و ظرفیت ویدیو {report.budget_seconds:.1f} ثانیه")
    parts.extend(report.hard_problems[:3])
    if review is not None:
        weak = [f"{item.criterion} {item.score:g}" for item in review.scores if item.score < 6 or (item.criterion in DECISIVE and (not item.verified or item.score < 7))]
        if weak:
            parts.append("معیارهای زیر حد قبولی: " + "، ".join(weak[:4]))
        parts.extend(review.must_fix[:2])
    return "؛ ".join(dict.fromkeys(part for part in parts if part))
