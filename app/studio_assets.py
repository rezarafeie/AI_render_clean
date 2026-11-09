"""What a storyboard job has prepared so far (pictures, narration, clips), for the chat's step log. Reads files only; nothing is generated."""
from __future__ import annotations

import json
from pathlib import Path

SERVABLE = {".jpg", ".jpeg", ".png", ".webp", ".mp3", ".wav", ".m4a", ".mp4", ".webm"}
RENDER_STAGES_FA = {
    "building mlt": "آماده‌سازی برنامهٔ رندر", "rendering": "رندر صحنه‌ها", "rendering motion scenes": "رندر موشن‌گرافیک صحنه‌ها",
    "adding poster to video": "افزودن پوستر به ویدیو", "checking export": "بررسی فایل خروجی",
    "reviewing creative output": "بازبینی کیفیت خلاقانهٔ خروجی", "checking reference fidelity": "بررسی تطابق با مرجع",
    "reviewing motion scenes": "بازبینی کیفیت صحنه‌های موشن", "designing motion scenes": "طراحی صحنه‌های موشن توسط طراح",
}


def render_detail(message) -> str:
    text = str(message or "").strip()
    return RENDER_STAGES_FA.get(text.lower(), text if any("؀" <= c <= "ۿ" for c in text) else "")


def _safe(job_dir: Path, value) -> str | None:
    try:
        path = Path(str(value))
        path = (path if path.is_absolute() else job_dir / path).resolve()
        root = job_dir.resolve()
        if root in path.parents and path.is_file() and path.suffix.lower() in SERVABLE and not path.name.startswith("."):
            return path.relative_to(root).as_posix()
    except (OSError, ValueError):
        pass
    return None


def collect(job_dir: Path, scenes: list[dict], checkpoint: dict | None = None) -> list[dict]:
    """One entry per prepared file: {kind: image|video|motion|audio, scene (1-based), label, file, duration_s?, text?}."""
    checkpoint = checkpoint or {}
    media = {m.get("scene_index"): m for m in checkpoint.get("media", []) if isinstance(m, dict)}
    voice = {n.get("scene_index"): n for n in checkpoint.get("narration", []) if isinstance(n, dict)}
    out: list[dict] = []
    for position, scene in enumerate(scenes):
        index = scene.get("index", position)
        number = (index if isinstance(index, int) else position) + 1
        image = _safe(job_dir, scene["source_asset"]) if scene.get("source_asset") else None
        if image:
            out.append({"kind": "image", "scene": number, "label": f"تصویر صحنهٔ {number}", "src": image})
        clip = media.get(index)
        file = _safe(job_dir, clip.get("file_path")) if clip else None
        if file:
            motion = scene.get("motion_engine") == "motion_so"
            out.append({"kind": "motion" if motion else "video", "scene": number,
                        "label": f"{'کلیپ موشن' if motion else 'کلیپ'} صحنهٔ {number}", "src": file,
                        "duration_s": clip.get("duration_s")})
        said = voice.get(index)
        file = _safe(job_dir, said.get("file_path")) if said else None
        if file:
            out.append({"kind": "audio", "scene": number, "label": f"نریشن صحنهٔ {number}", "src": file,
                        "duration_s": said.get("duration_s"), "text": str(said.get("narration_text") or "")[:240]})
    return out


def from_job(job_dir: Path) -> list[dict]:
    try:
        scenes = json.loads((job_dir / "storyboard.json").read_text()).get("scenes", [])
    except (OSError, ValueError):
        return []
    try:
        checkpoint = json.loads((job_dir / "generated" / "generation_checkpoint.json").read_text())
    except (OSError, ValueError):
        checkpoint = {}
    return collect(job_dir, scenes, checkpoint)


def summary(assets: list[dict]) -> str:
    count = lambda kind: sum(1 for a in assets if a["kind"] == kind)
    parts = [f"{n} {name}" for kind, name in (("image", "تصویر"), ("video", "کلیپ"), ("motion", "کلیپ موشن"), ("audio", "فایل صوتی نریشن")) if (n := count(kind))]
    return "، ".join(parts)


def review_frames(job_dir: Path, report: dict | None) -> list[dict]:
    """The frames the creative review looked at, as prepared files for the step log (one group, in time order)."""
    out: list[dict] = []
    for i, frame in enumerate((report or {}).get("frames") or [], 1):
        src = _safe(job_dir, frame.get("path")) if isinstance(frame, dict) else None
        if src:
            at = frame.get("time")
            out.append({"kind": "image", "scene": i, "group": "فریم‌های نمونهٔ بازبینی", "label": f"فریم {i}" + (f" · ثانیهٔ {at:g}" if isinstance(at, (int, float)) else ""), "src": src})
    return out
