"""The motion/creative skills the studio can read on demand (vendor/motion-skills, MIT; see SOURCES.json for repositories, revisions and notices).

One index (vendor/motion-skills/index.json) feeds three consumers and nothing else is kept in memory:
  * the creative resource registry (creative/resources/providers.py -> skill_resources) so search, the agent tool and the HTTP API find them;
  * the planner: a compact one-line-per-skill catalogue; the planner names at most two skills it wants for this film (no extra model call);
  * the scene designers: only the bodies of the skills the planner chose, bounded, plus two short fixed blocks of craft rules.

The index is read the first time something asks (never at import or start-up); a skill body is read only when it is selected. Nothing here
executes anything: the vendored folders contain Markdown and text, no scripts. Ids can never be paths: only ids found in the index resolve.

The two fixed blocks below are short distillations of the craft rules of Hugh Phan's motion-kit (MIT) and of bang-motion's anti-slide principles
(MIT, Bang Tutorial); the full texts are the vendored skills `motionkit:motion-designer` and `bang:bang-motion`.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "vendor" / "motion-skills"
MAX_SELECTED = 2
BODY_CHARS = 2400


@lru_cache(maxsize=1)
def index() -> dict[str, dict]:
    try:
        rows = json.loads((DIR / "index.json").read_text(encoding="utf-8"))["skills"]
    except (OSError, ValueError, KeyError):
        return {}
    return {row["id"]: row for row in rows}


def get(skill_id: str) -> dict | None:
    return index().get(str(skill_id or ""))


def planner_eligible(row: dict) -> bool:
    """Skills the planner may choose: the ones that need no runtime or hardware the studio does not run."""
    return not row.get("runtime_needed")


def _first_sentence(text: str, limit: int = 78) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    cut = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    return (cut if len(cut) <= limit else cut[:limit].rsplit(" ", 1)[0] + "…")


def planning_block() -> str:
    """One line per skill the planner may pick, in the planner's prompt. Empty when the vendored library is missing."""
    rows = [r for r in index().values() if planner_eligible(r)]
    if not rows:
        return ""
    lines = [f"- {r['id']}: {r.get('hint') or _first_sentence(r['description'])}" for r in rows]
    return ("CRAFT SKILLS (optional). Name up to two skill ids in `skills` when their craft really fits this film (for example a kinetic-typography film, a product launch, "
            "a data story, an explainer); the scene designers then read those skills. Leave `skills` empty for a simple film.\n" + "\n".join(lines))


def normalize_ids(ids) -> list[str]:
    """The planner's choice, kept only if every id is a real, selectable skill (at most two, no duplicates)."""
    out: list[str] = []
    for value in ids or []:
        row = get(str(value).strip())
        if row and planner_eligible(row) and row["id"] not in out:
            out.append(row["id"])
    return out[:MAX_SELECTED]


def _strip_frontmatter(text: str) -> str:
    return re.sub(r"^---\s*\n.*?\n---\s*\n?", "", text, count=1, flags=re.S)


def body(skill_id: str, max_chars: int | None = None) -> str:
    """The skill's own instructions (front matter removed), cut at a paragraph boundary. '' for an unknown id. Reads the file now, not before."""
    row = get(skill_id)
    if not row:
        return ""
    try:
        path = (DIR / row["path"]).resolve()
        path.relative_to(DIR.resolve())
        text = _strip_frontmatter(path.read_text(encoding="utf-8")).strip()
    except (OSError, ValueError):
        return ""
    if max_chars and len(text) > max_chars:
        cut = text[:max_chars]
        text = cut[:cut.rfind("\n\n")] if "\n\n" in cut[max_chars // 2:] else cut
        text += "\n[… the rest is in the full skill]"
    return text


def reference(skill_id: str, name: str, max_chars: int = 6000) -> str:
    """One of the skill's own reference files, only if the index lists it."""
    row = get(skill_id)
    if not row:
        return ""
    wanted = next((r for r in row.get("references", []) if r.endswith("/" + name) or r == name), None)
    if not wanted:
        return ""
    try:
        path = (DIR / wanted).resolve()
        path.relative_to(DIR.resolve())
        return path.read_text(encoding="utf-8")[:max_chars]
    except (OSError, ValueError):
        return ""


def designer_block(ids) -> str:
    """What a scene designer reads: the craft rules every film gets, then the chosen skills (bounded)."""
    chosen = normalize_ids(ids)
    parts = [MOTION_CRAFT, COMPOSITION_CRAFT]
    for skill_id in chosen:
        text = body(skill_id, BODY_CHARS)
        if text:
            row = get(skill_id) or {}
            parts.append(f"SKILL «{skill_id}» (from {row.get('repo', '')}, {row.get('license', 'MIT')}). Use its craft where it fits this scene; the rules above and the scene's own limits come first:\n{text}")
    return "\n\n".join(parts)


def verify() -> dict:
    """Re-hash every vendored file against the index (a changed, missing or extra file is reported, never silently accepted). Reads all files: not for the request path."""
    import hashlib
    bad, count = [], 0
    for row in index().values():
        for rel, expected in row.get("files", {}).items():
            count += 1
            try:
                path = (DIR / rel).resolve()
                path.relative_to(DIR.resolve())
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
            except (OSError, ValueError):
                actual = None
            if actual != expected:
                bad.append(rel)
    allowed = {rel for row in index().values() for rel in row.get("files", {})}
    extra = sorted(str(p.relative_to(DIR)) for p in DIR.rglob("*") if p.is_file() and p.suffix not in {".json", ".LICENSE"} and p.name != "README.md" and str(p.relative_to(DIR)) not in allowed)
    return {"files": count, "mismatched": bad, "unlisted": extra, "ok": not bad and not extra}


def notices() -> list[dict]:
    """The attribution of every vendored source (repository, revision, licence file), for the UI and for audits."""
    try:
        return json.loads((DIR / "SOURCES.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


MOTION_CRAFT = (
    "MOTION CRAFT (the global `MotionKit` is loaded; GSAP timeline helpers, seek-safe: use them with the same `tl`, never as a second timeline). "
    "Move like a motion designer, not like a preset:\n"
    "- Give each property its own curve: MotionKit.curve('kit.land'|'kit.heavy'|'kit.whip'|'kit.reveal'|'kit.leave'|'kit.wind'|'kit.drift'|'m3.emphasizedDecelerate'|'easings.outExpo'…), or MotionKit.bez(x1,y1,x2,y2). "
    "Avoid ease:'power3.out' on everything.\n"
    "- Duration comes from distance and weight: MotionKit.dur(px, 0.7 light | 1 normal | 1.35 heavy). Exits are about 0.65x as long as entrances and accelerate out: MotionKit.exitTo(tl, el, {x,y}, at).\n"
    "- A lead and its reactions at uneven offsets: at + MotionKit.react(i) (0, 4, 9, 15, 22, 30 frames), never an even stagger. Travel on a bent path: MotionKit.arc(tl, el, {x,y}, {x:0,y:0}, at). "
    "Add a small counter-move before a decisive move: MotionKit.anticipate(tl, el, 'x', from, to, at). A child that lags its parent and settles last: MotionKit.drag.\n"
    "- Springs only on transforms (never opacity): const s = MotionKit.spring({response:.45, damping:.8}); tl.fromTo(el,{y:80},{y:0,duration:s.duration,ease:s.ease},at). Overshoot is a choice, not a garnish.\n"
    "- Text: a written line (a quote, a prompt, a typed command) types on: MotionKit.typeOn (a clip reveal that follows the text direction); other text cuts on (MotionKit.cut) or rises by whole words "
    "(MotionKit.revealWords(tl, el, at) with by:'words'); masked rises and blur-ins are the most overused moves, so use them rarely. "
    "Never animate letter-spacing (trackIn is not available in films: the renderer stutters on it). PERSIAN/ARABIC text must never be split into characters (by:'chars') "
    "or scrambled: that breaks the joined letters. Latin words and numbers may use MotionKit.scramble.\n"
    "- Holds stay alive: a slow camera drift or a small living detail, unless stillness is the point. About one signature device per film; craft every move, spend devices sparingly.")

COMPOSITION_CRAFT = (
    "COMPOSITION (anti-slide): a film states one thing per shot and lets motion carry the feeling; a scene that feels short of information is often right. "
    "No kicker + two-line title + body + chips stacked like a slide: one short line and one hero object. Keep ONE hero that persists across most of the film and changes "
    "role (moves, morphs, is carried into the next scene) instead of replacing every scene with a new page. Change shot size on purpose (close on the element that is being "
    "told, then wide), do not just breathe the camera a few percent. Different cuts use different moves; the same transition on every cut reads as a template. "
    "Backgrounds are alive and from the theme (gradient, paper, colour blocks, depth), never a flat colour or a crowd of bright particles behind text; glow belongs to objects, not headlines. "
    "Order of attention: the line first, then the hero, then supporting detail. Never invent numbers, logos or claims. These are craft guides, not rules that override the request: "
    "a simple, still or minimal film is right when that is what was asked.")
