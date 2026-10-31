"""Render owned, typed scene data with the repository's fixed React composition.

No code from a model or remote page is executed by this adapter.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render(config: dict, output: Path, *, job_dir: Path, on_progress=None, timeout: float | None = None) -> None:
    root = job_dir.resolve()
    config = json.loads(json.dumps(config))
    # The cinematic look is heavier to rasterise: it is opt-in per installation (REMOTION_LOOK=cinematic) until a render on that machine is measured.
    config["look"] = os.environ.get("REMOTION_LOOK", "classic")
    if config["look"] == "cinematic":
        _enrich(config, root)
    if not 1 <= len(config.get("scenes", [])) <= 30:
        raise ValueError("Motion scene count is outside render limits")
    if sum(scene.get("frames", 0) for scene in config["scenes"]) > 2700:
        raise ValueError("Motion duration exceeds 90 seconds")
    for scene in config["scenes"]:
        for field in ("asset", "narration"):
            if not scene.get(field):
                continue
            path = (root / scene[field]).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError(f"Invalid owned scene {field}")
            scene[field] = str(path)
        if not 1 <= scene["frames"] <= 900:
            raise ValueError("Scene duration is outside render limits")
        supporting = []
        stack = config.get('version')==3 and (scene.get('shotcraft') or {}).get('resource_id')=='shotcraft:card-stack'
        if stack and len(scene.get('supporting_assets',[]))!=9:
            raise ValueError('Native collection requires exactly nine owned images')
        for item in scene.get("supporting_assets", [])[:9 if stack else 3]:
            path = (root / item).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError("Invalid owned supporting asset")
            supporting.append(str(path))
        scene["supporting_assets"] = supporting
    if config.get("music"):
        music = Path(config["music"])
        if not music.is_absolute():
            music = root / music
        # Music is selected by the server from its approved library.
        music = music.resolve()
        if not (music.is_relative_to(root) or music.is_relative_to((ROOT / "assets/music").resolve())):
            raise ValueError("Music must belong to the job or approved library")
        if not music.is_file():
            raise ValueError("Music asset is missing")
        config["music"] = str(music.resolve())
    if config.get("version") == 3:
        from creative.shotcraft_native import parse_spec
        if len(config["scenes"]) != 1:
            raise ValueError("Native Shotcraft requires one typed component")
        parse_spec(config["scenes"][0].get("shotcraft"))
        config["font"] = str(ROOT / "presets/fonts/Vazirmatn-Regular.ttf")
    else:
        config["font"] = str(ROOT / "presets/fonts/RAY-EXTRABLACK.TTF")
    config_path = output.with_suffix(".remotion.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False))
    command = ["node", "render.mjs", str(config_path), str(output.resolve())]
    process = subprocess.Popen(command, cwd=ROOT / "remotion", stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    def stop():
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = float(os.environ.get("REMOTION_TIMEOUT_S", "5400"))
    timer = threading.Timer(min(deadline,timeout) if timeout is not None else deadline, stop)       # preserve the existing installation deadline unless a bounded component requests less
    timer.daemon = True
    timer.start()
    tail = deque(maxlen=30)
    last_progress = -1
    try:
        for line in process.stdout:
            tail.append(line)
            if line.startswith("REMOTION_PROGRESS ") and on_progress:
                progress = min(95, int(line.split()[-1]))
                if progress != last_progress:
                    on_progress(progress)
                    last_progress = progress
        if process.wait() != 0:
            raise RuntimeError("Remotion render failed: " + "".join(tail)[-1800:])
    finally:
        timer.cancel()
        stop()
        process.stdout.close()


def _enrich(config: dict, root: Path) -> None:
    """Scenes saved before the cinematic reel (no look, no caption text) get them now, from the job's own storyboard and photos."""
    scenes = config.get("scenes", [])
    if not scenes or all("kind" in scene for scene in scenes):
        return
    from engine.persian_text import join_lam_alef
    from engine.remotion_prep import prepare
    try:
        board = json.loads((root / "storyboard.json").read_text()).get("scenes", [])
    except (OSError, ValueError):
        board = []
    looks: dict[str, dict] = {}
    for index, scene in enumerate(scenes):
        if "kind" in scene or not scene.get("asset"):
            continue
        source = Path(scene["asset"])
        source = source if source.is_absolute() else root / source
        if not source.resolve().is_relative_to(root) or not source.is_file():
            continue
        key = str(source.resolve())
        if key not in looks:
            try:
                looks[key] = prepare(source, root / "generated" / "cutouts")
            except Exception:
                looks[key] = {"asset": key, "kind": "photo", "accent": None}
        look = looks[key]
        scene.update(asset=look["asset"], kind=look["kind"], accent=look["accent"], supporting_assets=[look["asset"]])
        if index < len(board):
            scene["narration_text"] = join_lam_alef(board[index].get("narration_text") or "")
            scene["title"] = join_lam_alef(board[index].get("text_overlay") or scene.get("title") or "")
    product = next((l["accent"] for l in looks.values() if l["kind"] == "cutout" and l["accent"]), None) \
        or next((l["accent"] for l in looks.values() if l["accent"]), None)
    if product:
        for scene in scenes:
            scene["accent"] = product


def prepare_reel_config(config: dict, job_dir: Path) -> dict:
    """The scene config with everything the HyperFrames reel needs: a look per scene, caption text, absolute owned paths. Never trusts a path outside the job."""
    root = job_dir.resolve()
    config = json.loads(json.dumps(config))
    _enrich(config, root)
    for scene in config.get("scenes", []):
        for field in ("asset", "narration"):
            if not scene.get(field):
                continue
            path = Path(scene[field])
            path = (path if path.is_absolute() else root / path).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError(f"Invalid owned scene {field}")
            scene[field] = str(path)
    if config.get("music"):
        music = Path(config["music"])
        music = (music if music.is_absolute() else root / music).resolve()
        if not (music.is_relative_to(root) or music.is_relative_to((ROOT / "assets/music").resolve())) or not music.is_file():
            raise ValueError("Music must belong to the job or approved library")
        config["music"] = str(music)
    return config


def scene_config(storyboard, media: list[dict], narration: list[dict], job_dir: Path, music: str | None) -> dict:
    from engine.persian_text import join_lam_alef
    from engine.remotion_prep import prepare
    voices = {item["scene_index"]: item for item in narration}
    sources = {item["scene_index"]: item for item in media}
    prepared: dict[str, dict] = {}
    scenes = []
    for scene in storyboard.scenes:
        source = sources[scene.index]
        voice = voices.get(scene.index)
        if scene.source_asset not in prepared:
            try:
                if os.environ.get("REMOTION_LOOK", "classic") != "cinematic":
                    raise RuntimeError("classic look keeps the original photos")
                prepared[scene.source_asset] = prepare(job_dir / scene.source_asset, job_dir / "generated" / "cutouts")
            except Exception:               # the original picture is always a valid fallback
                prepared[scene.source_asset] = {"asset": str(job_dir / scene.source_asset), "kind": "photo", "accent": None}
        look = prepared[scene.source_asset]
        asset = Path(look["asset"])
        try:
            asset = asset.relative_to(job_dir)
        except ValueError:
            asset = Path(scene.source_asset)
        scenes.append({"asset": str(asset), "kind": look["kind"], "accent": look["accent"],
                       "title": join_lam_alef(scene.text_overlay or ""), "narration_text": join_lam_alef(scene.narration_text or ""),
                       "role": scene.narrative_role, "visual_type": scene.visual_type, "motion_style": scene.motion_style,
                       "frames": max(1, round(source["duration_s"] * 30)),
                       "narration": str(Path(voice["file_path"]).relative_to(job_dir)) if voice else None})
        # Only use relevant assets explicitly selected by the storyboard.
        # No automatic gallery of unrelated product photos every third scene.
        scenes[-1]["supporting_assets"] = [str(asset)]
    # One accent for the whole reel: the product's own colour (from a cut-out product photo if there is one), not a backdrop's.
    product = next((look["accent"] for look in prepared.values() if look["kind"] == "cutout" and look["accent"]), None) \
        or next((look["accent"] for look in prepared.values() if look["accent"]), None)
    if product:
        for scene in scenes:
            scene["accent"] = product
    directed = any(scene.narrative_role for scene in storyboard.scenes)
    return {"scenes": scenes, "music": music, "version": 2 if directed else 1}
