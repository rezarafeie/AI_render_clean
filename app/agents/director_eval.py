"""Evaluation of the Director (Medium's planner) on real kinds of requests: what it DECIDES, before anything runs.

Each case is a conversation state (request, attachments, what the earlier rounds observed, the film or discovery this chat holds) and the behaviour the plan
must show: which tool comes first, which must not appear, whether it must ask instead of acting, words its answer must contain. The planner is called with
exactly the production prompt and tool catalog (app.agents.planner.PROMPT, tools.catalog()); no tool is executed.

    python -m app.agents.director_eval            # all cases, a table and a score
    python -m app.agents.director_eval raw_ask    # cases whose id contains the word
"""
from __future__ import annotations

import json
import sys
import time

from app.agents import planner
from app.agents.medium import tools
from app.agents.medium.state import EditingPlan

VIDEO = [{"id": "att_video", "kind": "video", "filename": "VID_20261116.mp4", "size_bytes": 48_000_000}]
LONG = [{"id": "att_long", "kind": "video", "filename": "podcast_episode_12.mp4", "size_bytes": 1_900_000_000}]
IMAGE = [{"id": "att_img", "kind": "image", "filename": "product.jpg", "size_bytes": 900_000}]

PRODUCED = {"tool": "look_at_media", "attachment_id": "att_video", "duration": 41.1, "size": [1080, 1920], "cuts_per_minute": 9.0, "lufs": -14.4, "kind": "produced_edit",
            "produced_level": 0.82, "burned_subtitles": True, "graphics_overlays": 0.65, "on_screen_text": 0.8, "has_speaker": True, "speaker_framing": "medium",
            "summary": "مردی دربارهٔ رابطه صحبت می‌کند؛ ویدیو تدوین‌شده است با زیرنویس سوخته، نوشته‌های درشت و تصاویر مکمل.", "weaknesses": ["نوشته‌های متعدد روی تصویر"],
            "produced": True, "advice": "ALREADY PRODUCED: ... ASK the person for the RAW footage ..."}
RAW = {"tool": "look_at_media", "attachment_id": "att_video", "duration": 58.0, "size": [1080, 1920], "cuts_per_minute": 0.0, "lufs": -22.0, "kind": "raw_talking",
       "produced_level": 0.05, "burned_subtitles": False, "graphics_overlays": 0.0, "on_screen_text": 0.0, "has_speaker": True, "speaker_framing": "medium",
       "summary": "زنی رو به دوربین دربارهٔ فروش اینترنتی صحبت می‌کند؛ یک نمای ثابت بدون تدوین.", "produced": False, "advice": "RAW footage: ..."}
LONG_LOOK = {**RAW, "attachment_id": "att_long", "duration": 3650.0, "summary": "یک پادکست دونفره یک ساعته، دو نمای ثابت.", "kind": "raw_talking"}
MOTION_DONE = {"id": "m1", "status": "completed", "title": "تورم چیست", "summary": "موشن‌گرافیک ۶۰ ثانیه‌ای", "versions": 1, "request": "یه موشن گرافیک درباره تورم"}
MOTION_ASKS = {"id": "m2", "status": "needs_input", "intro": "presenter", "versions": 0, "request": "یه ویدیوی معرفی با مجری برای برندم",
               "questions_asked": ["برای سبک «مجری» فوتیج خود مجری لازم است؛ ویدیو را بفرستید."]}

# expect: first = the first step's tool must be one of these ("" = no steps: an answer or a question); never = tools that must not appear;
# args = {tool: {argument: substring}}; says = words the summary must contain one of (when it answers instead of acting)
CASES = [
    {"id": "look_first_motion", "request": "موشن‌های این ویدیو رو بهتر کن و جذاب‌ترش کن", "assets": VIDEO, "expect": {"first": ["look_at_media"]}},
    {"id": "raw_ask_when_produced", "request": "موشن‌های این ویدیو رو بهتر کن و جذاب‌ترش کن", "assets": VIDEO, "observations": [PRODUCED],
     "expect": {"first": [""], "says": ["خام", "raw", "اصلی", "قبل از تدوین"]}},
    {"id": "raw_edit_when_raw", "request": "موشن‌های این ویدیو رو بهتر کن و جذاب‌ترش کن", "assets": VIDEO, "observations": [RAW],
     "expect": {"first": ["analyze_talking_reel"]}},
    {"id": "captions_only", "request": "فقط زیرنویس فارسی بذار روی این ویدیو، هیچ چیز دیگه‌ای نه", "assets": VIDEO, "observations": [RAW],
     "expect": {"first": ["analyze_talking_reel"], "args": {"analyze_talking_reel": {"captions_only": "True"}}}},
    {"id": "premium_named", "request": "این ویدیو رو با موتور پریمیوم تمام‌قاب ادیت کن", "assets": VIDEO, "observations": [RAW],
     "expect": {"first": ["analyze_talking_reel"], "args": {"analyze_talking_reel": {"variant": "premium"}}}},
    {"id": "long_to_reels", "request": "از این پادکست چندتا ریلز خوب دربیار", "assets": LONG, "observations": [LONG_LOOK], "expect": {"first": ["discover_clips"]}},
    {"id": "dub_english", "request": "این ویدیو رو به انگلیسی دوبله کن", "assets": VIDEO, "expect": {"first": ["look_at_media", "localize_video"]}},
    {"id": "vox", "request": "یه ویدیو به سبک ووکس درباره اینکه بیت‌کوین چطور ساخته شد", "expect": {"direction": True, "first": ["create_motion_graphic"], "args": {"create_motion_graphic": {"request": "ووکس"}}}},
    {"id": "explainer_3d", "request": "یه اکسپلینر سه‌بعدی درباره اینکه پرداخت آنلاین چطور کار می‌کنه بساز", "expect": {"direction": True, "first": ["create_motion_graphic"], "args": {"create_motion_graphic": {"request": "سه"}}}},
    {"id": "intro_story", "request": "یه ویدیوی معرفی به سبک قصه برای Notion بساز", "expect": {"first": ["create_motion_graphic"], "args": {"create_motion_graphic": {"request": "معرفی"}}}},
    {"id": "intro_vague", "request": "یه ویدیوی معرفی برای کسب‌وکارم بساز", "expect": {"first": [""], "says": ["چه", "کسب‌وکار", "لینک", "؟"]}},
    {"id": "product_link", "request": "از این محصول یه تبلیغ کوتاه بساز https://shop.example.com/p/123", "expect": {"first": ["inspect_url"]}},
    {"id": "motion_topic", "request": "یه موشن گرافیک ۴۵ ثانیه‌ای درباره قانون پارتو بساز", "expect": {"direction": True, "first": ["create_motion_graphic"]}},
    {"id": "greeting", "request": "سلام، چه کارهایی می‌تونی برام انجام بدی؟", "expect": {"first": [""], "never": ["create_motion_graphic", "analyze_talking_reel"]}},
    {"id": "answer_with_footage", "request": "اینم فوتیج مجری", "assets": VIDEO, "motion_graphic": MOTION_ASKS,
     "expect": {"first": ["answer_motion_graphic", "look_at_media"], "never": ["create_motion_graphic", "analyze_talking_reel"]}},
    {"id": "revise_voice", "request": "صدای نریشن رو با صدای خودم عوض کن", "motion_graphic": MOTION_DONE, "expect": {"first": ["revise_motion_graphic"], "never": ["create_motion_graphic"]}},
    {"id": "revise_pronunciation", "request": "تلفظ کلمه مرتب اشتباهه، مُرَتَّب درسته", "motion_graphic": MOTION_DONE, "expect": {"first": ["revise_motion_graphic"]}},
    {"id": "revise_ending", "request": "پایانش خیلی یهویی تموم میشه، یه پایان درست بذار", "motion_graphic": MOTION_DONE, "expect": {"first": ["revise_motion_graphic", "review_output"], "never": ["create_motion_graphic"]}},
    {"id": "new_subject", "request": "حالا یکی دیگه درباره بهره مرکب بساز", "motion_graphic": MOTION_DONE, "expect": {"first": ["create_motion_graphic"]}},
    {"id": "discovery_clip", "request": "کلیپ ۳ رو ادیت کن", "discovery": True, "expect": {"first": ["discovery_command"]}},
    {"id": "check_after_film", "request": "یه موشن گرافیک درباره قانون پارتو بساز", "motion_graphic": {**MOTION_DONE, "title": "قانون پارتو"},
     "observations": [{"tool": "create_motion_graphic", "label": "ساخت موشن‌گرافیک قانون پارتو", "motion_id": "m1", "job_finished": True,
                       "film": {"status": "completed", "versions": 1, "title": "قانون پارتو", "duration": 52.0, "notes": []}}],
     "expect": {"first": ["review_output"]}},
    {"id": "fix_after_review", "request": "یه موشن گرافیک درباره قانون پارتو بساز", "motion_graphic": {**MOTION_DONE, "title": "قانون پارتو"},
     "observations": [{"tool": "create_motion_graphic", "motion_id": "m1", "job_finished": True, "film": {"status": "completed", "versions": 1}},
                      {"tool": "review_output", "verdict": "fix", "score": 5, "matches_request": True, "ending": "abrupt",
                       "problems": [{"where": "50-52 s", "what": "the film stops mid-motion, no final frame", "fix": "end on the key sentence with a 1.5 s hold and the title"},
                                    {"where": "scenes 3-6", "what": "the same centred-title layout four times", "fix": "vary the layouts: a chart, a split, a full-bleed number"}]}],
     "expect": {"first": ["revise_motion_graphic"]}},
    {"id": "deliver_after_good_review", "request": "یه موشن گرافیک درباره قانون پارتو بساز", "motion_graphic": {**MOTION_DONE, "title": "قانون پارتو", "versions": 2},
     "observations": [{"tool": "revise_motion_graphic", "motion_id": "m1", "job_finished": True, "film": {"status": "completed", "versions": 2}},
                      {"tool": "review_output", "verdict": "deliver", "score": 8, "matches_request": True, "ending": "good", "problems": [], "praise": "پایان حالا روشن است."}],
     "expect": {"first": [""], "never": ["revise_motion_graphic", "create_motion_graphic"]}},
    {"id": "loudness", "request": "صدای این ویدیو کلیپ نمی‌کنه؟ بلندیش برای اینستاگرام درسته؟", "assets": VIDEO, "expect": {"first": ["audio_check"]}},
]


def _payload(case: dict) -> dict:
    context = {"request": case["request"], "current_project_id": None, "history": [{"role": "user", "content": case["request"]}],
               "assets": case.get("assets", []), "projects": [], "manual": False}
    if case.get("motion_graphic"):
        context["motion_graphic"] = case["motion_graphic"]
    if case.get("cloned_voice", True):
        context["person_has_cloned_voice"] = True
    if case.get("discovery"):
        context["discovery"] = {"analysis_id": "d1", "clips_found": 9, "note": "nine clip cards from the long video are in this chat"}
    from app.agents.medium.worker import Decision
    return {"context": context, "observations": case.get("observations", []), "turn": len(case.get("observations", [])) + 1, "tools": tools.catalog(),
            "decision_schema": Decision.model_json_schema()}


def decide(case: dict) -> dict:
    """The worker's decision for this state through exactly the production path (Opus lock, corrections by the same model): {summary, steps, model}."""
    from app.agents.medium.worker import ask
    d, problem = ask(_payload(case))
    if d is None:
        raise ValueError("no usable decision: " + problem)
    return {"summary": d.say, "steps": [d.action.model_dump()] if d.action else [], "model": d.__dict__.get("_model", "?")}


def score(case: dict, plan: dict) -> list[str]:
    """The failures (empty = pass)."""
    expect, steps = case["expect"], plan.get("steps") or []
    first = steps[0]["tool"] if steps else ""
    used = [s["tool"] for s in steps]
    out = []
    if "first" in expect and first not in expect["first"]:
        out.append(f"first={first or '(answer)'} expected {'/'.join(x or '(answer)' for x in expect['first'])}")
    for bad in expect.get("never", []):
        if bad in used:
            out.append(f"used {bad}")
    for tool, wanted in expect.get("args", {}).items():
        step = next((s for s in steps if s["tool"] == tool), None)
        for key, sub in wanted.items():
            if step is None or sub.lower() not in str(step.get("arguments", {}).get(key, "")).lower():
                out.append(f"{tool}.{key} lacks «{sub}»")
    if expect.get("direction"):
        step = next((s for s in steps if s["tool"] == "create_motion_graphic"), None)
        text = str((step or {}).get("arguments", {}).get("request", ""))
        empty = [w for w in ("خلاقانه", "جذاب", "حرفه‌ای", "انیمیشن‌های زیبا") if w in text.replace(case["request"], "")]
        if step and (len(text) - len(case["request"]) < 220 or empty):
            out.append(f"generic direction ({len(text) - len(case['request'])} chars added" + (f", empty words: {', '.join(empty)}" if empty else "") + ")")
    if expect.get("says") and not steps and not any(w.lower() in plan.get("summary", "").lower() for w in expect["says"]):
        out.append("the answer misses: " + " / ".join(expect["says"]))
    return out


def main(argv: list[str]) -> int:
    chosen = [c for c in CASES if not argv or any(a in c["id"] for a in argv)]
    passed, rows = 0, []
    for case in chosen:
        started = time.monotonic()
        try:
            plan = decide(case)
            fails = score(case, plan)
        except Exception as exc:
            plan, fails = {"summary": "", "steps": []}, [f"error: {str(exc)[:160]}"]
        passed += not fails
        steps = " → ".join(s["tool"] for s in plan.get("steps") or []) or "(answer)"
        rows.append(f"{'PASS' if not fails else 'FAIL'}  {case['id']:<24} {time.monotonic() - started:5.1f}s  [{plan.get('model', '?')}]  {steps}" + (f"\n      {'; '.join(fails)}" if fails else "")
                    + (f"\n      «{plan.get('summary', '')[:220]}»" if not plan.get("steps") else ""))
        print(rows[-1], flush=True)
    print(f"\nSCORE {passed}/{len(chosen)}")
    return 0 if passed == len(chosen) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
