"""Checks that need no model: the facts of a finished storyboard video that a viewer notices at once."""
from __future__ import annotations


def output_issues(storyboard: dict, *, music: bool, voice_ids: set[str], persian_voices: set[str]) -> list[str]:
    scenes = storyboard.get("scenes") or []
    issues: list[str] = []
    sources = [s.get("source_asset") for s in scenes if s.get("source_asset")]
    if len(scenes) >= 4 and sources and len(set(sources)) / len(scenes) < 0.6:
        issues.append(f"فقط {len(set(sources))} تصویر متفاوت برای {len(scenes)} صحنه استفاده شده؛ بیننده تکرار را می‌بیند.")
    if not music:
        issues.append("موزیک پس‌زمینه ندارد.")
    spoken = [s for s in scenes if (s.get("narration_text") or "").strip()]
    if spoken and voice_ids and not (voice_ids & persian_voices):
        issues.append("گوینده یک صدای فارسی تأییدشده نیست؛ تلفظ فارسی ممکن است خارجی باشد.")
    return issues
