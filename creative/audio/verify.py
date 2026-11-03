"""Check that narrated audio says what the script says, using speech recognition, and repair a failed scene at most once.

Recognition is evidence, not proof: it can show a missing sentence, the wrong language or a garbled word, but it cannot show
that a name sounds right. Work is bounded in time and in retries, and a check that cannot run says so instead of passing.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable

from .persian import is_persian
from .quality import completeness

_LATIN = re.compile(r"[A-Za-z]")
_ARABIC = re.compile(r"[؀-ۿ]")


def script_mismatch(expected: str, recognised: str) -> bool:
    """True when the expected text is mostly one script and the recognised text is mostly the other."""
    exp_fa = is_persian(expected)
    letters_latin = len(_LATIN.findall(recognised)); letters_arabic = len(_ARABIC.findall(recognised))
    if letters_latin + letters_arabic < 4:
        return False
    return (exp_fa and letters_latin > 2 * letters_arabic) or (not exp_fa and letters_arabic > 2 * letters_latin)


def verify_clips(texts: list[str], clips: list[tuple[Path, float]], recognise: Callable[[Path, int], str | None],
                 regenerate: Callable[[int], tuple[Path, float] | None], *, max_error: float = 0.35, budget_s: float = 120.0,
                 retries: int = 1, clock: Callable[[], float] = time.monotonic) -> tuple[list[tuple[Path, float]], list[dict]]:
    """Returns (clips, report). Each report row: scene, status (ok | repaired | needs_review | not_checked), error, retried."""
    started = clock()
    out, report = list(clips), []
    unavailable = 0                           # recognition that fails or returns nothing twice in a row is not going to work for the rest either
    for index, (text, clip) in enumerate(zip(texts, clips)):
        if not text.strip():
            continue
        row = {"scene": index + 1, "status": "not_checked", "error": None, "retried": 0}
        if unavailable >= 2:
            row["reason"] = "recognition unavailable (skipped after two failures)"; report.append(row); continue
        if clock() - started > budget_s:
            row["reason"] = "time budget used up"; report.append(row); continue
        try:
            heard = recognise(Path(clip[0]), index)
        except Exception as exc:
            heard = None; row["reason"] = type(exc).__name__
        if heard is None or not heard.strip():
            # No text came back at all: the recogniser failed or heard nothing it could use. That says nothing about the narration,
            # so it is "not checked", and above all it must not trigger another (paid) voicing.
            row.setdefault("reason", "recognition unavailable" if heard is None else "recognition returned no text"); report.append(row); unavailable += 1; continue
        unavailable = 0
        current = completeness(text, heard)["word_error_rate"]
        wrong_script = script_mismatch(text, heard)
        attempt = 0
        while (current > max_error or wrong_script) and attempt < retries and clock() - started <= budget_s:
            attempt += 1
            fresh = regenerate(index)
            if not fresh:
                break
            try:
                again = recognise(Path(fresh[0]), index)
            except Exception:
                again = None
            if again is None:
                break
            better = completeness(text, again)["word_error_rate"]
            if better < current or script_mismatch(text, heard) and not script_mismatch(text, again):
                out[index], current, heard, wrong_script = fresh, better, again, script_mismatch(text, again)
            row["retried"] = attempt
        row["error"] = round(current, 3)
        row["recognised"] = heard[:240]
        row["status"] = "needs_review" if (current > max_error or wrong_script) else ("repaired" if row["retried"] else "ok")
        if wrong_script:
            row["reason"] = "the recognised speech is in a different script than the script"
        report.append(row)
    return out, report
