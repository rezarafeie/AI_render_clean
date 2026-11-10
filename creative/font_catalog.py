"""The font library every engine designs with (assets/fonts_pro/catalog.json, built by scripts/build_font_catalog.py).

One list for: the planner (which fonts fit this film), the scene designers (exactly which families and weights exist), the vision step (specimen sheets it can look at),
the page builder (@font-face and the files for the families a page really uses) and the Edit tab (change the title or body font, with previews)."""
from __future__ import annotations

import json
import logging
import re
import shutil
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "assets" / "fonts_pro"
GENERIC = {"sans-serif", "serif", "monospace", "inherit", "cursive", "system-ui"}
DEFAULT_TITLE, DEFAULT_BODY = "ray", "ray"          # what films used before the catalog existed


@lru_cache(maxsize=1)
def load() -> tuple[dict, ...]:
    try:
        return tuple(json.loads((DIR / "catalog.json").read_text(encoding="utf-8"))["fonts"])
    except (OSError, ValueError, KeyError):
        return ()


def get(font_id: str) -> dict | None:
    return next((f for f in load() if f["id"] == font_id), None)


def by_family(family: str) -> dict | None:
    wanted = family.strip(" '\"").lower()
    return next((f for f in load() if any(c.lower() == wanted for c in f["css_families"])), None)


def allowed_families() -> set[str]:
    """Every CSS family name a page may use (lower case), the studio's own included."""
    names = {c.lower() for f in load() for c in f["css_families"]}
    return names | {"ray", "vazir", "kharazmi", "inter"}


def family_of(font_id: str, default: str = "Ray") -> str:
    font = get(font_id)
    return font["family"] if font else default


def resolve(font_id: str, default: str) -> str:
    return font_id if get(font_id) else default


# ── for the models ────────────────────────────────────────────────────────────────────────────────────────────────
def shortlist(full: bool = True) -> str:
    """The catalog as compact lines. `full` adds the avoid-list and the vendor's note (the vision step reads those; the planner gets the short form)."""
    lines = []
    for f in load():
        weights = f["weights"]
        span = f"{weights[0]}-{weights[-1]}" if len(weights) > 1 else str(weights[0] if weights else 400)
        axes = ", ".join(f"{k} {v[0]}-{v[1]}" for k, v in f.get("axes", {}).items() if k != "wght")
        families = f["css_families"]
        css = f"'{families[0]}'" + (f" (shapes: {', '.join(families)})" if len(families) > 1 else "")
        line = (f"- {f['id']} · {css} · {span}{' · axes ' + axes if axes else ''} · {'Latin+Persian' if f.get('latin') else 'PERSIAN ONLY'} · {', '.join(f['mood'][:3])} · for: "
                f"{', '.join(f['best_for'][:3])}")
        if full:
            line += f" · avoid: {', '.join(f['avoid_for']) or '-'} · {f['note']}"
        lines.append(line)
    return "\n".join(lines)


def sheets() -> list[Path]:
    return sorted((DIR / "sheets").glob("sheet-*.jpg"))


def planning_block() -> str:
    return ("FONT LIBRARY (choose from it; the ids and CSS family names are exact):\n" + shortlist(full=False) +
            "\nRules: pick `title_font` (headlines, big numbers) and `body_font` (labels, callouts, small text) as ids from this list; they may be the same. Pair a display font with a calm one "
            "(for example a heavy display title with `aramesh` or `paykan` body). A PERSIAN ONLY font must never carry Latin text. Weights outside a font's range are not available.")


def designer_block(title_id: str, body_id: str) -> str:
    """What a scene designer is told about fonts: the film's two fonts, exactly how to write them, and the other families it may reach for once."""
    t, b = get(title_id) or get(DEFAULT_TITLE), get(body_id) or get(DEFAULT_BODY)
    if not t or not b:
        return ""

    def spec(f: dict) -> str:
        weights = f["weights"]
        span = f"{weights[0]}-{weights[-1]}" if len(weights) > 1 else str(weights[0] if weights else 400)
        axes = [k for k in f.get("axes", {}) if k != "wght"]
        tail = f"; animate or set the axes {', '.join(axes)} with font-variation-settings" if axes else ""
        return f"font-family: '{f['family']}' (weights {span}{tail}{'; no Latin letters' if not f.get('latin') else ''})"

    other = ", ".join(f"'{f['family']}'" for f in load() if f["id"] not in {t["id"], b["id"]})
    return (f"FONTS OF THIS FILM: headlines and big numbers use {spec(t)}. Labels, callouts and small text use {spec(b)}. Do not write font-family names other than these two, except "
            f"one accent family for a single special moment, chosen only from: {other}. Write numbers as Persian digits (۰-۹) in Persian text.")


# ── page building ─────────────────────────────────────────────────────────────────────────────────────────────────
_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}]+)", re.I)
_SHORTHAND_RE = re.compile(r"font\s*:\s*[^;}]*", re.I)


def used_families(*texts: str) -> list[str]:
    """The catalog families (CSS names) a page's styles ask for."""
    blob = "\n".join(t or "" for t in texts)
    found: list[str] = []
    known = {c.lower(): c for f in load() if not f.get("builtin") for c in f["css_families"]}
    for match in _FAMILY_RE.finditer(blob):
        for part in match.group(1).split(","):
            name = part.strip(" '\"")
            if name.lower() in known and known[name.lower()] not in found:
                found.append(known[name.lower()])
    for match in _SHORTHAND_RE.finditer(blob):                      # `font: 900 80px/1.3 Doran`
        for family in known.values():
            if re.search(rf"(?<![\w-])['\"]?{re.escape(family)}['\"]?(?![\w-])", match.group(0)) and family not in found:
                found.append(family)
    return found


def faces_css(families: list[str]) -> str:
    out = []
    for family in families:
        font = by_family(family)
        if not font or font.get("builtin"):
            continue
        for face in font["faces"]:
            if face["css_family"].lower() != family.lower():
                continue
            weight = face["weight"]
            out.append(f"@font-face{{font-family:'{face['css_family']}';src:url('./assets/fonts/pro/{Path(face['file']).name}');font-weight:{weight};font-style:normal}}")
    return "".join(out)


def copy_assets(destination: Path, families: list[str]) -> list[str]:
    """Copy the files of `families` next to the page (destination = the project's assets/fonts)."""
    target = destination / "pro"
    copied: list[str] = []
    for family in families:
        font = by_family(family)
        if not font or font.get("builtin"):
            continue
        for face in font["faces"]:
            if face["css_family"].lower() != family.lower():
                continue
            source = DIR / face["file"]
            if source.is_file():
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target / source.name)
                copied.append(source.name)
    return copied


def swap_family(text: str, old: str, new: str) -> str:
    """Replace one font family by another in CSS/HTML/JS of a saved design (declarations and the `font:` shorthand), quoting the new name."""
    if not old or not new or old.lower() == new.lower():
        return text
    pattern = re.compile(rf"(?<![\w-])(['\"]?){re.escape(old)}\1(?![\w-])", re.I)

    def declaration(match: re.Match) -> str:
        return pattern.sub(f"'{new}'", match.group(0))
    text = _FAMILY_RE.sub(declaration, text)
    return _SHORTHAND_RE.sub(declaration, text)


# ── vision ────────────────────────────────────────────────────────────────────────────────────────────────────────
ADVISE_SYSTEM = (
    "You are the typography director of a Persian motion-design studio. You are given contact sheets of the studio's font library (each specimen is labelled with the font id at the top) "
    "and a short description of the film. LOOK at the specimens and choose the fonts whose real shapes fit this film best: a title font for headlines and big numbers and a body font "
    "for labels and small text (they may be the same family). Judge by how the letters look, not only by the notes. A font marked PERSIAN ONLY has no Latin letters. "
    "Return ONLY JSON: {\"title_font\": id, \"body_font\": id, \"accent_font\": id or \"\", \"why\": one Persian sentence that names what you saw in the shapes}.")


def advise(brief: str, tone: str = "") -> dict:
    """The vision model looks at the specimen sheets and picks the title/body fonts for a film. {} when it cannot (the planner then chooses from the text list)."""
    images = sheets()
    if not images or not load():
        return {}
    try:
        from brain.llm import chat_vision
        user = f"FILM:\n{brief.strip()[:1800]}\n" + (f"TONE: {tone}\n" if tone else "") + "\nFONT LIBRARY (ids and notes):\n" + shortlist()
        data, _usage = chat_vision(ADVISE_SYSTEM, user, images=[str(p) for p in images], return_json=True, max_tokens=700, timeout_seconds=150, route="font_advisor")
    except Exception as exc:
        log.warning("font advice by vision failed: %s", str(exc)[:200])
        return {"error": str(exc)[:200]}
    if not isinstance(data, dict):
        return {}
    chosen = {k: str(data.get(k) or "") for k in ("title_font", "body_font", "accent_font")}
    chosen = {k: (v if get(v) else "") for k, v in chosen.items()}
    chosen["why"] = str(data.get("why") or "")[:400]
    return chosen
