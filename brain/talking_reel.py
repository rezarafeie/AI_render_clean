"""Edit decisions for talking-head reels (podcast clips) with the configured LLM.

The model gets the transcript sentences (with indices) and returns:
corrected caption text per sentence, the pinned hook title with its
highlighted words, sentences to drop, a few emotional sentences to show in
black and white, and up to two short emphasis phrases. Timing
stays with the transcript; the model only edits text and picks indices.

There is no silent local fallback: a reel without corrected captions and a
hook is not worth rendering, so provider failures raise.
"""
from __future__ import annotations

import json
import logging
import re

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You edit short vertical reels cut from Persian business podcasts, in the style of
popular Persian business creators on Instagram. You receive the transcript as numbered
sentences (speech-to-text output, colloquial Tehrani Persian). Return ONLY a JSON object:

{
  "hook": "<pinned hook title in Persian, 3-8 words, a curiosity gap that makes people keep
           watching, usually first person and ending with ... when it teases; must be faithful
           to what the speaker actually says>",
  "hook_highlight": ["<1-2 words or short phrases copied exactly from hook to show in yellow; ALWAYS at least one, the word that carries the curiosity>"],
  "captions": [{"i": <sentence index>, "text": "<corrected caption>"}],
  "drop": [<indices of sentences to cut: filler, false starts, an off-topic "yes"/"ok" at the end>],
  "bw": [<3-6 indices of the most emotional, dramatic or insightful sentences, spread over the WHOLE talk (roughly one every 20-30 seconds of speech), shown in black and white>],
  "notes": [{"i": <index of one of the "bw" sentences>, "text": "<2-4 word punchy key takeaway of it>"}],
  "cold_open": {"i": <sentence index>, "text": "<the line of the talk that makes a stranger stop scrolling, copied word for word from that
                sentence's transcript (a contiguous part of it, 6-14 words, about 3-5 seconds), played first as a teaser
                before the video starts from the beginning>"}
}

The cold open is the most important choice of the reel. It must be a COMPLETE, SELF-CONTAINED claim that works with no context:
a surprising fact or number, a bold or contrarian statement, the payoff or the promise of the talk, or a sharp emotional line.
Never pick a lead-in, a greeting, a fragment, a transition ("خب"، "یعنی"، "پس"، "حالا"), a scene-setting action ("میریم دم یخچال")
or a sentence that starts with a pronoun or a reference to something said before. It must come from the body or the end of the
talk, never from its first sentences (the video starts there anyway). Check it against the hook: together they must make the viewer ask "why?".

Caption rules:
- One caption entry for EVERY sentence index that is not dropped, in order.
- Fix every speech-to-text mistake (wrong letters, wrong words, missing spaces, half-space
  where needed) using the context; keep the speaker's colloquial wording (میخوام، نمیخواد، اینه).
- Remove hesitation sounds and stutters (اِاِاِ، امم، اوم) and immediate word repeats.
- Keep English terms the speaker says in Latin script (e.g. scalable, Drop Servicing).
- Write numbers with Persian digits.
- Do not add words the speaker did not say. Do not summarise.
Pick several key moments, not one: "bw" has 3 to 6 sentences (fewer only when the talk is under a minute) and "notes" gives
each of them its takeaway (at most 5 notes). Each note is shown alone, word by word, over its
black-and-white moment: write it in Persian words only (no English words, no Latin script)."""

FILLER_WORDS = re.compile(r"^(?:[اآ]+[ِ]?)+$|^(?:ا?م+|ا?و?م+|ا?ه+)$")

STYLE_SELECTOR_PROMPT = """Choose the best edit style for a Persian talking-head reel from its transcript.
Return ONLY JSON: {"style":"talking_1|talking_2|talking_3|talking_4","reason":"short Persian reason"}.
Use talking_1 for energetic personal-brand clips that benefit from bold hooks and punchy zooms.
Use talking_2 for practical education, lists, tools, steps, or concrete explanations where a few minimal illustrations help.
Use talking_3 for emotional stories, dramatic ideas, or reflective narratives that benefit from cinematic chapter cards.
Use talking_4 for calm, authentic speaker-led clips where generated visuals would distract. Prefer talking_4 when uncertain."""


def _sentences_prompt(sentences: list[dict]) -> str:
    rows = [f"{k}: [{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for k, s in enumerate(sentences)]
    return "Transcript sentences:\n" + "\n".join(rows)


def _chat(system: str, user: str) -> dict:
    from .lm_gateway import configured
    if configured():
        from .llm import gateway_json_resilient
        data, _ = gateway_json_resilient(system, user, "editing_agent")
        return data
    from .ai_provider import ArvanProvider

    errors = []
    provider = ArvanProvider()
    for attempt in range(3):
        try:
            data, usage = provider._chat_json(system, user)
            log.info("talking reel decisions from %s (%s)", provider.name, usage.model)
            return data
        except Exception as exc:  # hosted links may fail transiently
            errors.append(f"attempt {attempt + 1}: {exc}")
            log.warning("talking reel Arvan AI attempt failed: %s", exc)
    raise RuntimeError("Arvan AI unavailable for the talking reel: " + " | ".join(errors)[:600])


def recommend_style(sentences: list[dict]) -> tuple[str, str]:
    """Select a talking-reel style before rendering and explain it to the editor."""
    data = _chat(STYLE_SELECTOR_PROMPT, _sentences_prompt(sentences))
    style = str(data.get("style") or "").strip()
    if style not in {"talking_1", "talking_2", "talking_3", "talking_4"}:
        style = "talking_4"
    reason = str(data.get("reason") or "").strip()
    return style, reason


def guidance_block(guidance: str = "") -> str:
    """Creative direction from ``creative/`` appended to the user prompt (empty when there is none)."""
    return f"\n\n{guidance.strip()}" if guidance and guidance.strip() else ""


def decide(sentences: list[dict], guidance: str = "") -> dict:
    """Ask the LLM for text edits and highlights; returns validated decisions."""
    if not sentences:
        raise ValueError("no speech in the transcript")
    data = _chat(SYSTEM_PROMPT, _sentences_prompt(sentences) + guidance_block(guidance))
    return normalize(data, len(sentences))


def normalize(data: dict, count: int) -> dict:
    """Validate indices and fill gaps so rendering never depends on a perfect answer."""
    def index(value) -> int | None:
        try:
            k = int(value)
        except (TypeError, ValueError):
            return None
        return k if 0 <= k < count else None

    drop = sorted({k for k in (index(v) for v in data.get("drop") or []) if k is not None})
    captions = {}
    for item in data.get("captions") or []:
        k = index((item or {}).get("i"))
        text = str((item or {}).get("text") or "").strip()
        if k is not None and text and k not in drop:
            captions[k] = text
    bw = [k for k in (index(v) for v in data.get("bw") or []) if k is not None and k not in drop][:6]
    notes = []
    for item in data.get("notes") or []:
        k = index((item or {}).get("i"))
        text = str((item or {}).get("text") or "").strip()
        # Emphasis phrases are Persian only.
        if k is not None and text and k not in drop and len(text.split()) <= 5 and not re.search(r"[A-Za-z]", text):
            notes.append({"i": k, "text": text})
    cold = data.get("cold_open") or {}
    cold_i = index(cold.get("i")) if isinstance(cold, dict) else None
    cold_open = ({"i": cold_i, "text": str(cold.get("text") or "").strip()}
                 if cold_i is not None and cold_i not in drop else None)
    hook = str(data.get("hook") or "").strip()
    if not hook:
        raise RuntimeError("the LLM returned no hook title")
    highlight = [str(h).strip() for h in data.get("hook_highlight") or [] if str(h).strip() and str(h).strip() in hook]
    return {"hook": hook, "hook_highlight": highlight[:2] or default_highlight(hook), "captions": captions, "drop": drop,
            "bw": bw, "notes": notes[:5], "cold_open": cold_open}


def default_highlight(hook: str) -> list[str]:
    """The hook always has a yellow word: when the model named none, the longest word (the first of equals), punctuation left out."""
    words = [w for w in (re.sub(r"[^\w\u200c]", "", part) for part in hook.split()) if len(w) >= 3]
    if not words:
        return []
    best = max(words, key=len)
    return [best] if best in hook else []


def is_filler(word: str) -> bool:
    """Hesitation tokens that the cut should remove (اِاِاِ، امم، ...)."""
    return bool(FILLER_WORDS.match(re.sub(r"[^\w؀-ۿ]", "", word or "")))
