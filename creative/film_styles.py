"""The film-style library (vendor/motion-skills, namespace `lemo`: 99 Lemo-Opuscar styles) for the engines that write their own code: Claude motion and Vox.

    catalog()                 the whole library in one line per style, for the director's (cached) system prompt
    menu(brief, avoid)        the per-film note: styles this person's recent films used
    guide(style_id)           the style's digest for the art and scene writers, with the studio's adaptation rules on top ("" when unknown)
    recent(directory)         what this person's last films looked like (title, look, style): the director must not make the same film again
    valid(style_id)           a real film style id, or ""

The director chooses ONE style (or none) and says in its look how THIS film bends it; a style is a design language (palette, type, motion, camera), never a template.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)
MENU_SIZE = 22
ADAPT = ("ADAPTING THIS STYLE TO THE STUDIO (these come first): Persian, right to left; Persian text is never animated letter by letter (whole words, word by word, "
         "or a wipe from the right); the frame and safe zones of THIS film's format; only the kit, the fonts and the files this engine gives you (the style's own "
         "tools, engines, fonts, footage, music and demo assets do not exist here: reach the same feeling with what exists); never copy the style's demo film, its "
         "characters, mascots, logos or any brand; numbers and facts come only from this film's brief. Take its colour logic, type attitude, motion quality, "
         "camera grammar and native moves.")


def _rows() -> list[dict]:
    try:
        from creative import skills_library
        return [r for r in skills_library.index().values() if r.get("namespace") == "lemo" and r["id"] != "lemo:director-method" and not r.get("runtime_needed")]
    except Exception:
        log.warning("film-style library unavailable", exc_info=True)
        return []


def valid(style_id: str | None) -> str:
    value = str(style_id or "").strip()
    if value and not value.startswith("lemo:"):
        value = "lemo:" + value
    return value if any(r["id"] == value for r in _rows()) else ""


def catalog() -> str:
    """The whole library, one short line per style: identical for every film, so it sits in the director's system prompt (read from the provider's cache)."""
    rows = sorted(_rows(), key=lambda r: r["id"])
    if not rows:
        return ""
    lines = [f"- {r['id'][5:]}: {(r.get('hint') or r.get('description') or '').split(' Good for:')[0][:120]}" for r in rows]
    return ("FILM-STYLE LIBRARY (Lemo-Opuscar, 99 film languages: palette, type, motion and camera of a whole film). Choose ONE id for `style` when it gives THIS "
            "subject a stronger, more specific look than a generic explainer, or leave it empty; then write in `look` how this film bends it (its own palette, one "
            "signature motif). Choose for the subject and audience, never the first or a familiar one.\n" + "\n".join(lines))


def menu(brief: str, avoid: list[str] | None = None) -> str:
    """The per-film part: the styles this person's recent films already used (the director must not repeat them)."""
    skip = sorted({valid(a) for a in (avoid or [])} - {""})
    return ("STYLES NOT TO USE THIS TIME (this person's recent films used them): " + ", ".join(x[5:] for x in skip)) if skip else ""


def guide(style_id: str | None, limit: int = 5600) -> str:
    sid = valid(style_id)
    if not sid:
        return ""
    from creative import skills_library
    body = skills_library.body(sid, limit) or ""
    return f"THIS FILM'S STYLE «{sid}» (Lemo-Opuscar by Lemomo (LemoLab)):\n{ADAPT}\n\n{body}" if body else ""


def recent(directory: Path, count: int = 6) -> list[dict]:
    """This person's last films made by Claude motion or Vox (any chat), newest first, without the one in `directory`: {title, look, style, engine}."""
    try:
        user_root = Path(directory).resolve().parents[2]            # job_data/studio/<user>/<conversation>/motion/<id>
        files = [p for p in user_root.glob("*/motion/*/claude_motion.json") if p.parent.resolve() != Path(directory).resolve()]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except (OSError, IndexError):
        return []
    out = []
    for path in files[:count * 2]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("vox"):
            s = data.get("story") or {}
            out.append({"engine": "vox", "title": s.get("title", ""), "look": f"{s.get('look', '')}: {s.get('look_note', '')}"[:300], "style": s.get("style", "")})
        elif data.get("direction"):
            d = data["direction"]
            out.append({"engine": f"intro {data['intro']}" if data.get("intro") else "motion", "title": d.get("title", ""), "look": (d.get("look") or "")[:300], "style": d.get("style", "")})
        if len(out) >= count:
            break
    return out


def recent_block(items: list[dict]) -> str:
    if not items:
        return ""
    rows = "\n".join(f"- «{i['title']}» ({i['engine']}{', style ' + i['style'] if i.get('style') else ''}): {i['look']}" for i in items)
    return ("THIS PERSON'S RECENT FILMS (newest first). This film must not look like them: a different ground, palette, type attitude and art language, unless the "
            "person asks for the same look:\n" + rows)
