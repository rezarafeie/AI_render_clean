"""Content Creator orchestrator — generates Instagram content from a text prompt."""
from __future__ import annotations

import json
import hashlib
import logging
import math
import os
import subprocess
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from app.celery_app import CELERY_AVAILABLE
from app.config import settings
from request_context import celery_request_headers
from engine.content_types import ContentType, get_preset
from engine.schema import PROJECT_ROOT, validate_plan
from .storyboard import Storyboard, Scene, generate_storyboard
from .media_provider import get_provider, list_providers, MediaResult, still_to_motion_video

log = logging.getLogger(__name__)


def _save_checkpoint(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    temporary.replace(path)


def _load_checkpoint(path: Path, signature: str, provider_name: str) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text())
            # Completed scene files are reusable when a failed job is retried
            # with another provider. The storyboard signature is the content
            # identity; provider choice only affects scenes that still need media.
            if isinstance(data, dict):
                matched = data.get('signature') == signature
                if not matched:
                    # Cross-version reuse is permitted only with component
                    # identities. Never bless a legacy row after input changes.
                    data['media']=[r for r in data.get('media',[]) if isinstance(r,dict) and r.get('fingerprint')]
                    data['narration']=[r for r in data.get('narration',[]) if isinstance(r,dict) and r.get('fingerprint')]
                data['legacy_signature_match']=matched
                data['signature']=signature
                data["provider"] = provider_name
                return data
        except (OSError, ValueError, TypeError):
            pass
    return {"signature": signature, "provider": provider_name, "media": [], "narration": []}


def _voice_provider() -> str:
    """All generated speech uses the same ElevenLabs route as Localize."""
    return "elevenlabs"


def _default_narration_voice(language: str) -> str:
    """Choose a native locale voice for Content Creator's default narration."""
    normalized = language.lower().strip()
    if normalized in {"fa", "per", "fas", "persian", "farsi"}:
        return os.environ.get("CONTENT_TTS_VOICE_FA", "fa-IR-DilaraNeural").strip() or "fa-IR-DilaraNeural"
    return os.environ.get("CONTENT_TTS_VOICE_EN", "en-US-GuyNeural").strip() or "en-US-GuyNeural"


def _default_elevenlabs_voice(language: str) -> str:
    """Return Localize's canonical ElevenLabs voice for every TTS surface."""
    from .localize import tts_voice
    return tts_voice()


def create_content(
    prompt: str,
    content_type: str,
    language: str = "fa",
    style: str = "rafiei_reel",
    provider_name: str = "arvan_image",
    creative_brief: Optional[dict[str, str]] = None,
    user_id: Optional[str] = None,
    source_assets: Optional[list[Path]] = None,
    creative_plan: dict | None = None,
    asset_catalog: list[dict] | None = None,
    duration: float = 30,
) -> dict:
    from app.jobs import create_job, _write_status

    ct = ContentType(content_type)
    get_provider(provider_name)
    brief = {key: str((creative_brief or {}).get(key, "")).strip()[:500]
             for key in ("audience", "goal", "brand", "avoid")}
    brief = {key: value for key, value in brief.items() if value}
    content_llm_provider = os.environ.get(
        "CONTENT_LLM_PROVIDER", settings.CONTENT_LLM_PROVIDER
    ).strip().lower()
    asset_catalog = asset_catalog if asset_catalog is not None else []
    if source_assets:
        from brain.product_assets import inspect_assets, catalog_prompt
        if not asset_catalog:
            asset_catalog = inspect_assets([Path(item).resolve() for item in source_assets[:20]], prompt)
        prompt += catalog_prompt(asset_catalog)
    if creative_plan is not None:
        from creative.schemas import CreativePlan
        from creative.production import storyboard_from_plan
        # public creative state deliberately preserves the chosen concept and
        # facts. Only the compiler below selects real supported scene actions.
        plan = CreativePlan.model_validate({**creative_plan,
            'concepts':creative_plan.get('concepts') or [creative_plan['chosen']],
            'critique':creative_plan.get('critique') or {'chosen_id':creative_plan['chosen']['id']}})
        storyboard = storyboard_from_plan(plan,prompt=prompt,language=language,style=style,
            duration=duration,asset_indices={row['index'] for row in asset_catalog},brief=brief)
    else:
        storyboard = generate_storyboard(
            prompt, ct, language, style, brief,
            provider_name=content_llm_provider or None,
        )
    if storyboard.is_fallback:
        raise ValueError('برنامه‌ریز سناریو در دسترس نیست؛ پیش‌نویس نمایشی برای تولید نهایی پذیرفته نمی‌شود.')

    job = create_job(user_id=user_id)
    generated_dir = job.dir / "generated"
    generated_dir.mkdir(exist_ok=True)
    if creative_plan:
        _save_checkpoint(job.dir/'creative_plan.json',creative_plan)

    safe_assets: list[str] = []
    if source_assets:
        import shutil
        asset_dir = generated_dir / "source_assets"
        asset_dir.mkdir(exist_ok=True)
        asset_map = {}
        for index, original in enumerate(source_assets[:20]):
            if asset_catalog and index not in {row["index"] for row in asset_catalog}:
                continue
            source = Path(original).resolve()
            if not source.is_file():
                continue
            suffix = source.suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            target = asset_dir / f"asset_{index + 1:02d}{suffix}"
            shutil.copy2(source, target)
            safe_assets.append(str(target.relative_to(job.dir)))
            asset_map[index] = safe_assets[-1]
        if not safe_assets:
            raise ValueError("No valid source images were supplied")
        _save_checkpoint(generated_dir/'asset_map.json',asset_map)
        for index, scene in enumerate(storyboard.scenes):
            scene.media_method = "upload"
            if asset_catalog and scene.source_asset_index not in asset_map:
                raise ValueError(f"Scene {index + 1} did not select a verified product image; revise the storyboard")
            scene.source_asset = asset_map.get(scene.source_asset_index, safe_assets[index % len(safe_assets)])
    if asset_catalog:
        (generated_dir / "asset_catalog.json").write_text(json.dumps(asset_catalog, ensure_ascii=False, indent=2))

    storyboard_path = job.dir / "storyboard.json"
    storyboard_path.write_text(
        json.dumps(storyboard.to_dict(), indent=2, ensure_ascii=False)
    )

    if (creative_brief or {}).get('motion_engine')=='motion_so':
        for scene in storyboard.scenes:
            scene.motion_engine='motion_so'
        (job.dir/'storyboard.json').write_text(json.dumps(storyboard.to_dict(),ensure_ascii=False,indent=2))
    gen_status = {
        "state": "pending",
        "scenes_done": 0,
        "scenes_total": len(storyboard.scenes),
        "cost_so_far": 0.0,
        "cost_status": "not_started",
        "content_type": content_type,
        "provider": provider_name,
    }
    (job.dir / "generation_status.json").write_text(json.dumps(gen_status, indent=2))

    _write_status(job)

    return {"job_id": job.id, "storyboard": storyboard.to_dict()}


def _check_narration_timing(storyboard, segments: list[dict], gen_dir: Path, warnings: list) -> None:
    """Compare the plan with the real text-to-speech audio: the spoken length is the authority, not the estimate."""
    from creative import speech
    texts = {scene.index: scene.narration_text for scene in storyboard.scenes}
    estimated = sum(speech.speech_seconds(texts.get(row["scene_index"], "")) for row in segments)
    actual = sum(float(row.get("duration_s") or 0) for row in segments)
    planned = float(storyboard.total_duration_s or 0)
    report = {"estimated_s": round(estimated, 2), "actual_s": round(actual, 2), "planned_video_s": planned,
              **speech.check_audio(estimated, actual)}
    try:
        (gen_dir / "narration_check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    except OSError:
        pass
    if planned and actual > planned * 1.05:
        warnings.append(f"نریشن واقعی {actual:.1f} ثانیه شد و از مدت برنامه‌ریزی‌شده ({planned:g} ثانیه) بیشتر است؛ ویدیو با نریشن هماهنگ می‌شود و طولانی‌تر خواهد بود.")


def get_storyboard(job_id: str) -> Optional[dict]:
    from app.jobs import get as get_job
    job = get_job(job_id)
    if not job:
        return None
    sb_path = job.dir / "storyboard.json"
    if not sb_path.exists():
        return None
    return json.loads(sb_path.read_text())


def update_storyboard(job, scenes: list[dict], narrator: Optional[str] = None, voice_style: Optional[str] = None) -> Optional[dict]:
    sb_path = job.dir / "storyboard.json"
    if not sb_path.exists():
        return None

    sb_data = json.loads(sb_path.read_text())
    gs_path = job.dir / "generation_status.json"
    if gs_path.exists() and json.loads(gs_path.read_text()).get("state") == "generating":
        raise ValueError("Wait for generation to finish before editing the storyboard")
    if not scenes:
        raise ValueError("The storyboard must contain at least one scene")
    normalized = []
    for index, scene in enumerate(scenes):
        try:
            scene = Scene(**{**scene, "index": index}).to_dict()
            duration = float(scene["duration_s"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Scene {index + 1} is invalid") from exc
        if not math.isfinite(duration) or duration < 0.5:
            raise ValueError(f"Scene {index + 1} duration must be at least 0.5 seconds")
        scene["duration_s"] = duration
        normalized.append(scene)
    scenes = normalized
    preset = get_preset(sb_data["content_type"])
    if preset["is_static"] and (len(scenes) != 1 or scenes[0]["duration_s"] != 5):
        raise ValueError("A post must contain one 5-second scene")
    if preset["max_duration"] and sum(s["duration_s"] for s in scenes) > preset["max_duration"]:
        raise ValueError(f"Total duration must not exceed {preset['max_duration']} seconds")
    from .localize import VOICE_STYLES, narrator_ids
    if narrator is not None:
        if narrator and narrator not in narrator_ids():
            raise ValueError("This narrator is not available")
        sb_data["narrator"] = narrator
    if voice_style is not None:
        if voice_style not in VOICE_STYLES:
            raise ValueError("This voice style is not available")
        sb_data["voice_style"] = voice_style
    sb_data["scenes"] = scenes
    sb_data["total_duration_s"] = round(sum(s.get("duration_s", 0) for s in scenes), 2)
    sb_data["estimated_total_cost"] = round(sum(s.get("estimated_cost", 0) for s in scenes), 4)

    versions=job.dir/'storyboard_versions'
    versions.mkdir(exist_ok=True)
    previous=json.loads(sb_path.read_text())
    _save_checkpoint(versions/f'{time.time_ns()}-{uuid.uuid4().hex[:8]}.json',previous)
    sb_path.write_text(json.dumps(sb_data, indent=2, ensure_ascii=False))

    gen_status_path = job.dir / "generation_status.json"
    if gen_status_path.exists():
        gs = json.loads(gen_status_path.read_text())
        gs["scenes_total"] = len(scenes)
        gen_status_path.write_text(json.dumps(gs, indent=2))

    return sb_data


def get_storyboard_status(job) -> Optional[dict]:
    gs_path = job.dir / "generation_status.json"
    if not gs_path.exists():
        return None
    return json.loads(gs_path.read_text())


def approve_and_generate(job, provider_name: Optional[str] = None, *, retry_confirmed: bool = False) -> None:
    import fcntl
    with (job.dir/'.media-submit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _approve_and_generate(job,provider_name,retry_confirmed=retry_confirmed)


def _approve_and_generate(job, provider_name: Optional[str] = None, *, retry_confirmed: bool = False) -> None:
    gs_path = job.dir / "generation_status.json"
    gs = json.loads(gs_path.read_text()) if gs_path.exists() else {}
    if gs.get("state") == "generating":
        return
    if gs.get('state') == 'failed' and not retry_confirmed:
        raise ValueError('تلاش مجدد تولید مدیا هزینه دارد و نیازمند تأیید صریح شماست.')
    if any(s.get('motion_engine')=='motion_so' for s in json.loads((job.dir/'storyboard.json').read_text()).get('scenes',[])):
        from .motion_so import configured
        if not configured():raise ValueError('Motion is disabled or its API key is missing')

    provider_name = provider_name or gs.get("provider") or "local_fixture"
    try:
        provider = get_provider(provider_name)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc
    if not provider.has_key:
        raise ValueError(f"Provider {provider_name} is not configured")

    gs["state"] = "generating"
    authorization_id=uuid.uuid4().hex
    gs['authorization_id']=authorization_id
    gs["provider"] = provider_name
    gs.pop("error", None)
    gs_path.write_text(json.dumps(gs, indent=2))

    if CELERY_AVAILABLE:
        from app.tasks import task_generate_content
        task_generate_content.apply_async(
            args=(job.id, {"provider_name": provider_name, 'authorization_id':authorization_id}),
            headers=celery_request_headers(),
        )
    else:
        threading.Thread(
            target=_run_generation, args=(job.id, provider_name), kwargs={'authorization_id':authorization_id}, daemon=True
        ).start()


from brain.lm_gateway import job_scope


@job_scope
def _run_generation(job_id: str, provider_name: str, *, raise_errors: bool = False, authorization_id: str | None = None) -> None:
    from app.jobs import get as get_job, _write_status

    job = get_job(job_id)
    if not job:
        return

    gs_path = job.dir / "generation_status.json"
    sb_path = job.dir / "storyboard.json"
    gen_dir = job.dir / "generated"
    gen_dir.mkdir(exist_ok=True)

    try:
        if provider_name != 'local_fixture' or any(s.get('motion_engine')=='motion_so' for s in json.loads(sb_path.read_text()).get('scenes',[])):
            import re
            status=json.loads(gs_path.read_text())
            if not authorization_id or not re.fullmatch('[a-f0-9]{32}',authorization_id) or status.get('authorization_id') != authorization_id:
                raise ValueError('Fresh user authorization is required for media generation')
            claim=gen_dir/f'.attempt-{authorization_id}.claimed'
            try:
                descriptor=os.open(claim,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                os.close(descriptor)
            except FileExistsError:
                return  # Duplicate delivery cannot alter the original attempt's state or submit media.
        provider = get_provider(provider_name)
        sb_data = json.loads(sb_path.read_text())
        storyboard = Storyboard.from_dict(sb_data)
        content_type = ContentType(storyboard.content_type)
        preset = get_preset(content_type)
        signature = hashlib.sha256(json.dumps(sb_data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        checkpoint_path = gen_dir / "generation_checkpoint.json"
        checkpoint = _load_checkpoint(checkpoint_path, signature, provider_name)
        # Validate casting before generating any paid visuals. A missing Persian
        # voice must not be discovered only after all images have been charged.
        voice_provider = _voice_provider()
        from .localize import tts_model
        from .speech_policy import identity as casting_identity
        casting_context = f"{content_type} {storyboard.style} {sb_data.get('title', '')} {storyboard.creative_brief}"
        spoken_script = " ".join(s.narration_text or "" for s in storyboard.scenes)
        from .localize import VOICE_STYLES, narrator_ids
        chosen_voice = storyboard.narrator if storyboard.narrator in narrator_ids() else ""
        style_tags = VOICE_STYLES.get(storyboard.voice_style, VOICE_STYLES[""])[1]
        voice_signature = ((casting_identity(spoken_script,
                           _default_elevenlabs_voice(storyboard.language), tts_model(),
                           language=storyboard.language, context=casting_context) + (f"|{chosen_voice}|{style_tags}" if chosen_voice or style_tags else ""))
                           if spoken_script.strip() else "no-narration")
        from creative.reuse import media_identity, reusable, fingerprint
        media_pool=list(checkpoint.get('media',[]))
        cached_media = {
            m["scene_index"]: m for m in checkpoint["media"]
            if isinstance(m, dict) and Path(m.get("file_path", "")).is_file()
        }

        generated_media: list[dict] = []
        total_cost = 0.0
        cost_reported = True

        for scene in storyboard.scenes:
            try:
                identity=media_identity(scene,job.dir,preset['aspect'],preset['is_static'])
                reuse=reusable(media_pool,identity,scene.index,legacy=checkpoint.get('legacy_signature_match',False))
                if reuse:
                    record = reuse
                else:
                    if scene.motion_engine=='motion_so':
                        if preset['is_static']:raise ValueError('Motion video scenes are not supported in static posts')
                        from .motion_so import generate_scene
                        def motion_status(value):
                            current=json.loads(gs_path.read_text());current['motion_so']=value
                            _save_checkpoint(gs_path,current)
                        result=generate_scene(scene,job.dir,preset['aspect'],on_status=motion_status)
                    elif scene.media_method == "upload":
                        source = (job.dir / scene.source_asset).resolve()
                        if not source.is_relative_to(job.dir.resolve()) or not source.is_file():
                            raise ValueError(f"Scene {scene.index + 1} source image is missing")
                        result = still_to_motion_video(
                            source, gen_dir, scene.duration_s, preset["aspect"],
                            source="uploaded_image_motion",
                            metadata={"source_asset": scene.source_asset},
                        )
                    elif preset["is_static"]:
                        result = provider.generate_image(
                            scene.media_prompt or scene.description,
                            preset["aspect"],
                            gen_dir,
                        )
                    else:
                        result = provider.generate_video(
                            scene.media_prompt or scene.description,
                            scene.duration_s,
                            preset["aspect"],
                            gen_dir,
                        )
                    record = {
                        "scene_index": scene.index,
                        "file_path": result.file_path,
                        "source": result.source,
                        "cost_usd": result.cost_usd,
                        "generation_id": result.generation_id,
                        "width": result.width,
                        "height": result.height,
                        "duration_s": result.duration_s,
                        "fps": result.fps,
                        "metadata": result.metadata,
                        "fingerprint":identity,
                        "reused":False,
                    }
                if record["cost_usd"] is None:
                    cost_reported = False
                else:
                    total_cost += record["cost_usd"]
                generated_media.append(record)
                cached_media[scene.index] = record
                checkpoint["media"] = [cached_media[index] for index in sorted(cached_media)]
                _save_checkpoint(checkpoint_path, checkpoint)

                gs = json.loads(gs_path.read_text())
                gs["scenes_done"] = len(generated_media)
                gs["cost_so_far"] = round(total_cost, 4) if cost_reported else None
                gs["cost_status"] = "reported" if cost_reported else "not_reported_by_provider"
                gs_path.write_text(json.dumps(gs, indent=2))

            except Exception as exc:
                log.error("scene %d generation failed: %s", scene.index, exc)
                gs = json.loads(gs_path.read_text())
                gs["state"] = "failed"
                gs["error"] = f"Scene {scene.index}: {exc}"
                gs_path.write_text(json.dumps(gs, indent=2))
                if raise_errors:
                    raise
                return

        narration_segments: list[dict] = []
        warnings: list[str] = []
        if checkpoint.get("voice_signature") != voice_signature:
            checkpoint["narration"] = []
        checkpoint["voice_signature"] = voice_signature
        cached_narration = {
            n["scene_index"]: n for n in checkpoint["narration"]
            if isinstance(n, dict) and Path(n.get("file_path", "")).is_file()
            and n.get("provider") == "elevenlabs"
        }
        voice_pool=list(cached_narration.values())
        try:
            from .tts import generate_narration
            for scene in storyboard.scenes:
                if not isinstance(scene.narration_text, str) or not scene.narration_text.strip():
                    continue
                try:
                    identity=fingerprint({'text':scene.narration_text,'voice':voice_signature,'language':storyboard.language})
                    reuse=reusable(voice_pool,identity,scene.index,
                        legacy=checkpoint.get('legacy_signature_match',False))
                    if reuse and reuse.get("narration_text") == scene.narration_text:
                        record = reuse
                    else:
                        voice_kwargs = {
                            "voice_id": chosen_voice or _default_elevenlabs_voice(storyboard.language),
                            "model_id": "eleven_v3" if chosen_voice else tts_model(),     # the person's pick is used as chosen (eleven_v3 understands the style tags)
                        }
                        if not voice_kwargs["voice_id"]:
                            raise ValueError("Set an ElevenLabs voice ID for generated narration.")
                        tts_result = generate_narration(
                            (style_tags + scene.narration_text) if style_tags else scene.narration_text, gen_dir, provider="elevenlabs", language=storyboard.language,
                            context=casting_context, **voice_kwargs,
                        )
                        record = {
                            "scene_index": scene.index,
                            "narration_text": scene.narration_text,
                            "file_path": tts_result.file_path,
                            "duration_s": tts_result.duration_s,
                            "provider": "elevenlabs",
                            "fingerprint":identity,
                            "reused":False,
                        }
                    if preset["is_static"]:
                        record = _fit_post_narration(record, gen_dir, preset, warnings)
                    narration_segments.append(record)
                    cached_narration[scene.index] = record
                    checkpoint["narration"] = [cached_narration[index] for index in sorted(cached_narration)]
                    _save_checkpoint(checkpoint_path, checkpoint)
                except Exception as tts_exc:
                    raise RuntimeError(f"Voiceover failed for scene {scene.index + 1}: {tts_exc}") from tts_exc
        except ImportError as exc:
            if any(scene.narration_text for scene in storyboard.scenes):
                raise RuntimeError("Voiceover requires the ElevenLabs provider") from exc

        if narration_segments and not preset["is_static"]:
            _check_narration_timing(storyboard, narration_segments, gen_dir, warnings)

        if preset["is_static"]:
            if not generated_media:
                raise RuntimeError("Static content generation produced no media")
            still_path = generated_media[0]["file_path"]
            image_export = job.dir / "exports" / "post.png"
            image_export.parent.mkdir(exist_ok=True)
            import shutil
            shutil.copy2(still_path, image_export)
            motion = still_to_motion_video(
                still_path,
                gen_dir,
                5.0,
                preset["aspect"],
                generation_id=generated_media[0].get("generation_id", ""),
                cost_usd=generated_media[0].get("cost_usd"),
                source=f"{generated_media[0].get('source', 'image')}_motion",
                metadata=generated_media[0].get("metadata") or {},
            )
            generated_media[0].update({
                "file_path": motion.file_path,
                "source": motion.source,
                "width": motion.width,
                "height": motion.height,
                "duration_s": motion.duration_s,
                "fps": motion.fps,
                "metadata": motion.metadata,
            })
            source_path = motion.file_path

        narration_path = None
        if narration_segments:
            if content_type in (ContentType.STORY, ContentType.REEL):
                _fit_limited_narration(
                    generated_media, narration_segments, gen_dir, preset,
                    content_type, warnings,
                )
                checkpoint["narration"] = narration_segments
                _save_checkpoint(checkpoint_path, checkpoint)
            _fit_video_to_narration(generated_media, narration_segments, gen_dir, preset, warnings)
            checkpoint["media"] = generated_media
            _save_checkpoint(checkpoint_path, checkpoint)
            narration_path = _concat_audio(narration_segments, gen_dir, generated_media)

        if not preset["is_static"]:
            source_path = _stitch_videos(generated_media, gen_dir, preset)

        background_music_path = None
        music_source = None
        try:
            from .asset_match import music_match
            from engine.library import scan_category
            from engine.probe import probe
            music_candidates = [] if background_music_path else (music_match(top_n=5) or scan_category("music"))
            for asset in music_candidates:
                candidate = Path(asset.path)
                if not candidate.is_absolute():
                    candidate = PROJECT_ROOT / candidate
                try:
                    if candidate.is_file() and any(
                        stream.get("codec_type") == "audio"
                        for stream in probe(candidate).get("streams", [])
                    ):
                        background_music_path = str(candidate)
                        music_source = "library"
                        break
                except Exception as exc:
                    log.warning("Skipping unreadable background music %s: %s", candidate.name, exc)
        except Exception as exc:
            log.warning("Background music lookup skipped: %s", exc)
        if not background_music_path:
            warnings.append("No playable background music was found in the library. Add or upload music in the plan editor.")

        provenance_path = gen_dir / "provenance.json"
        provenance_path.write_text(
            json.dumps(generated_media, indent=2, ensure_ascii=False)
        )

        plan_data = storyboard_to_plan(
            storyboard, generated_media, content_type, source_path,
            narration_path=narration_path,
            background_music_path=background_music_path,
        )
        plan_data["generation_meta"]["warnings"] = warnings
        plan_data["generation_meta"]["voice_provider"] = voice_provider if narration_segments else None
        plan_data["generation_meta"]["music_source"] = music_source
        if (job.dir/'creative_plan.json').is_file():
            plan_data['generation_meta']['creative_plan']=json.loads((job.dir/'creative_plan.json').read_text())
        if not preset["is_static"] and all(scene.media_method == "upload" and scene.motion_engine=='default' for scene in storyboard.scenes):
            from engine.remotion_renderer import scene_config
            plan_data["generation_meta"]["renderer"] = "remotion"
            plan_data["generation_meta"]["remotion"] = scene_config(
                storyboard, generated_media, narration_segments, job.dir, background_music_path,
            )
        if music_source == "generated_music" and plan_data.get("music"):
            plan_data["music"]["volume_db"] = -18.0
        job.plan_data = plan_data

        job.raw_name = None
        _write_status(job)

        gs = json.loads(gs_path.read_text())
        gs["state"] = "ready"
        gs.pop("error", None)
        gs["warnings"] = warnings
        gs["cost_so_far"] = round(total_cost, 4) if cost_reported else None
        gs["cost_status"] = "reported" if cost_reported else "not_reported_by_provider"
        gs_path.write_text(json.dumps(gs, indent=2))

    except Exception as exc:
        log.exception("content generation failed for job %s", job_id)
        gs = json.loads(gs_path.read_text())
        gs["state"] = "failed"
        gs["error"] = str(exc)
        gs_path.write_text(json.dumps(gs, indent=2))
        if raise_errors:
            raise


def _stitch_videos(media: list[dict], gen_dir: Path, preset: dict) -> str:
    if len(media) == 1:
        return media[0]["file_path"]

    concat_list = gen_dir / "concat.txt"
    lines = []
    for m in media:
        fp = m["file_path"].replace("'", "'\\''")
        lines.append(f"file '{fp}'")
    concat_list.write_text("\n".join(lines))

    out_path = gen_dir / "stitched.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(out_path),
    ], capture_output=True, check=True, timeout=120)

    return str(out_path)


def _fit_video_to_narration(
    media: list[dict], narration: list[dict], gen_dir: Path,
    preset: dict, warnings: list[str],
) -> None:
    """Extend visuals modestly to preserve narration without creating long holds."""
    by_scene = {item["scene_index"]: item for item in narration}
    targets = []
    for item in media:
        current = float(item["duration_s"])
        voice = by_scene.get(item["scene_index"])
        target = max(current, round(float(voice["duration_s"]) + 0.2, 2)) if voice else current
        targets.append(target)
    if preset["is_static"] and targets[0] > 5.0:
        raise ValueError("Post voiceover exceeds 5 seconds; shorten its script before generating")
    if preset["max_duration"] and sum(targets) > preset["max_duration"] + 0.01:
        raise ValueError(
            f"Voiceover needs {sum(targets):.1f}s, above the {preset['max_duration']}s "
            "limit. Shorten the scripts in the storyboard."
        )

    max_stretch = float(preset.get("max_scene_stretch", 1.15))
    for item, target in zip(media, targets):
        current = float(item["duration_s"])
        if target > current * max_stretch + 0.08:
            raise ValueError(
                f"Scene {item['scene_index'] + 1} narration needs {target:.1f}s, "
                f"but its visual can be held for at most {current * max_stretch:.1f}s. "
                "Shorten that scene's script in the storyboard."
            )

    for item, target in zip(media, targets):
        current = float(item["duration_s"])
        if target <= current + 0.1:
            continue
        source = Path(item["file_path"])
        out = gen_dir / f"timed_scene_{item['scene_index']}.mp4"
        ratio = target / current
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-i", str(source),
            "-vf", f"setpts={ratio:.8f}*(PTS-STARTPTS),fps={preset['fps']},format=yuv420p",
            "-t", str(target), "-an", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "20", "-movflags", "+faststart", str(out),
        ], capture_output=True, check=True, timeout=max(60, round(target * 12)))
        item["file_path"] = str(out)
        item["duration_s"] = target
        item["metadata"] = {**item.get("metadata", {}), "original_duration_s": current,
                            "timing_adjustment": "stretched_to_fit_narration"}
        warnings.append(f"Scene {item['scene_index'] + 1}: visual duration extended to fit voiceover.")


def _fit_post_narration(
    record: dict, gen_dir: Path, preset: dict, warnings: list[str],
) -> dict:
    """Keep every approved word while fitting moderate speech into a five second post."""
    from .tts import _get_audio_duration

    duration = float(record["duration_s"])
    if duration <= 4.8:
        return record
    target = 4.65  # reserve room for encoder padding and the final pause
    speed = duration / target
    max_speed = float(preset.get("max_narration_speed", 1.15))
    if speed > max_speed:
        raise ValueError(
            f"Post voiceover is {duration:.1f}s and would need more than "
            f"{max_speed:.2f}x speech speed. "
            "Shorten the approved script in the storyboard."
        )
    source = Path(record["file_path"])
    output = gen_dir / f"narration_post_fit_{record['scene_index']}.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(source),
        "-filter:a", f"atempo={speed:.6f}", "-c:a", "libmp3lame", "-q:a", "2",
        str(output),
    ], capture_output=True, check=True, timeout=60)
    fitted_duration = _get_audio_duration(str(output))
    if not 0 < fitted_duration <= 4.8:
        output.unlink(missing_ok=True)
        raise RuntimeError("Post voiceover could not be fitted within five seconds")
    warnings.append(
        f"Post voiceover speed adjusted to {speed:.2f}x to preserve the approved script."
    )
    return {**record, "file_path": str(output), "duration_s": fitted_duration,
            "original_duration_s": duration, "timing_adjustment": "sped_up_for_post"}


def _fit_limited_narration(
    media: list[dict], narration: list[dict], gen_dir: Path,
    preset: dict, content_type: ContentType, warnings: list[str],
) -> None:
    """Fit Story or Reel speech within duration and natural pacing limits."""
    from .tts import _get_audio_duration

    if content_type not in (ContentType.STORY, ContentType.REEL):
        raise ValueError("narration fitting is for Stories and Reels")
    label = content_type.value.capitalize()
    limit = float(preset["max_duration"])
    max_speed = float(preset.get("max_narration_speed", 1.15))
    max_stretch = float(preset.get("max_scene_stretch", 1.15))
    by_scene = {item["scene_index"]: item for item in narration}
    base = sum(float(item["duration_s"]) for item in media)
    if base > limit + 0.01:
        raise ValueError(f"{label} visuals already exceed the {limit:g}s limit")

    def total_at(speed: float) -> float:
        return sum(max(
            float(item["duration_s"]),
            round(float(by_scene[item["scene_index"]]["duration_s"]) / speed + 0.2, 2),
        ) if item["scene_index"] in by_scene else float(item["duration_s"])
                   for item in media)

    def stretch_speed_needed() -> float:
        needed = 1.0
        for item in media:
            voice = by_scene.get(item["scene_index"])
            if voice is None:
                continue
            current = float(item["duration_s"])
            required = float(voice["duration_s"]) + 0.2
            if required > current * max_stretch:
                needed = max(needed, float(voice["duration_s"]) / (current * max_stretch - 0.2))
        return needed

    needed_speed = stretch_speed_needed()
    if needed_speed > max_speed + 0.001:
        raise ValueError(
            f"{label} voiceover needs {needed_speed:.2f}x speed to fit its scene visuals, "
            f"above the natural pacing limit of {max_speed:.2f}x. "
            "Shorten the affected scripts in the storyboard."
        )
    if total_at(1.0) <= limit + 0.01 and needed_speed <= 1.001:
        return
    # Leave a little room for MP3 padding and frame rounding, unless the
    # approved visuals already consume nearly all available time.
    target_total = max(base, limit - 0.15)
    if total_at(max_speed) > target_total + 0.001:
        raise ValueError(
            f"{label} voiceover cannot fit within {limit:g}s at "
            f"{max_speed:.2f}x speech speed. "
            "Shorten the approved scripts in the storyboard."
        )
    low, high = max(1.0, needed_speed), max_speed
    for _ in range(24):
        mid = (low + high) / 2
        if total_at(mid) <= target_total:
            high = mid
        else:
            low = mid
    speed = min(max_speed, high * 1.002)
    for record in narration:
        scene_media = next((m for m in media if m["scene_index"] == record["scene_index"]), None)
        if scene_media is None or float(record["duration_s"]) + 0.2 <= float(scene_media["duration_s"]):
            continue
        original_duration = float(record["duration_s"])
        source = Path(record["file_path"])
        output = gen_dir / f"narration_{content_type.value}_fit_{record['scene_index']}_{uuid.uuid4().hex[:8]}.mp3"
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-i", str(source),
            "-filter:a", f"atempo={speed:.6f}", "-c:a", "libmp3lame", "-q:a", "2",
            str(output),
        ], capture_output=True, check=True, timeout=60)
        fitted_duration = _get_audio_duration(str(output))
        if fitted_duration <= 0:
            output.unlink(missing_ok=True)
            raise RuntimeError(f"{label} voiceover could not be fitted")
        record.update(file_path=str(output), duration_s=fitted_duration,
                      original_duration_s=original_duration,
                      timing_adjustment=f"sped_up_for_{content_type.value}")
    if total_at(1.0) > limit + 0.01:
        raise RuntimeError(f"{label} voiceover could not be fitted within the duration limit")
    warnings.append(f"{label} voiceover speed adjusted to {speed:.2f}x to preserve the approved scripts.")


def _concat_audio(segments: list[dict], gen_dir: Path, media: list[dict]) -> str:
    """Assemble scene narration with silence for gaps, trimmed to scene lengths."""
    if not segments:
        raise ValueError("no narration segments")
    by_scene = {s["scene_index"]: s["file_path"] for s in segments}
    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    total_duration = 0.0
    for index, scene_media in enumerate(media):
        duration = float(scene_media["duration_s"])
        if duration <= 0:
            raise ValueError("scene media has no positive duration")
        total_duration += duration
        audio_file = by_scene.get(scene_media["scene_index"])
        if audio_file:
            inputs.extend(["-i", audio_file])
        else:
            inputs.extend(["-f", "lavfi", "-t", str(duration),
                           "-i", "anullsrc=r=44100:cl=stereo"])
        label = f"scene{index}"
        filters.append(
            f"[{index}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"apad,atrim=duration={duration:.6f},asetpts=PTS-STARTPTS[{label}]"
        )
        labels.append(f"[{label}]")

    filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[out]")
    out_path = gen_dir / "narration_full.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", *inputs,
        "-filter_complex", ";".join(filters), "-map", "[out]",
        "-t", str(total_duration), "-c:a", "libmp3lame", str(out_path),
    ], capture_output=True, check=True, timeout=120)
    return str(out_path)


def storyboard_to_plan(
    storyboard: Storyboard,
    generated_media: list[dict],
    content_type: ContentType,
    source_path: str,
    narration_path: Optional[str] = None,
    background_music_path: Optional[str] = None,
) -> dict:
    preset = get_preset(content_type)

    segments = []
    captions = []
    cursor = 0.0
    fps = preset["fps"]

    def _snap(t: float) -> float:
        return round(t * fps) / fps

    for scene in storyboard.scenes:
        media = next(
            (m for m in generated_media if m["scene_index"] == scene.index), None
        )
        if not media:
            continue

        if preset["is_static"]:
            dur = 5.0
        elif media.get("duration_s", 0) > 0:
            dur = media["duration_s"]
        else:
            dur = scene.duration_s

        dur = _snap(dur)

        seg_id = f"s{scene.index + 1}"
        segments.append({
            "id": seg_id,
            "in": 0.0 if preset["is_static"] else _snap(cursor),
            "out": dur if preset["is_static"] else _snap(cursor + dur),
            "zoom": {"from": 1.0, "to": 1.0},
        })

        if scene.text_overlay:
            cap_start = _snap(cursor)
            cap_end = _snap(cap_start + dur)
            if len(storyboard.scenes) > 1 and scene.index == 0:
                caption_style = "cover"
            elif len(storyboard.scenes) > 1 and scene.index == len(storyboard.scenes) - 1:
                caption_style = "cta"
            else:
                caption_style = "normal"
            captions.append({
                "start": round(cap_start, 3),
                "end": round(min(cap_end, cap_start + dur), 3),
                "text": scene.text_overlay,
                "style": caption_style,
            })

        cursor += dur

    if not segments:
        raise ValueError("no segments could be built from storyboard")

    plan = {
        "version": "0.1",
        "style": storyboard.style,
        "canvas": {
            "width": preset["width"],
            "height": preset["height"],
            "fps": preset["fps"],
        },
        "source": source_path,
        "segments": segments,
        "visual_effects": [
            {"segment_id": s["id"], "type": "steady__neutral"} for s in segments
        ],
        "transitions": [],
        "captions": captions,
        "broll": [],
        "music": (
            {"file": background_music_path, "volume_db": -24.0, "duck": []}
            if background_music_path else None
        ),
        "sfx": (
            [{"at": 0.0, "file": narration_path, "volume_db": 0.0}]
            if narration_path else []
        ),
        "export": {"file": "exports/v1.mp4", "crf": 20},
        "content_type": content_type.value,
        "source_type": "generated",
        "generation_meta": {
            "provider": generated_media[0]["source"] if generated_media else "unknown",
            "total_cost": (
                round(sum(m["cost_usd"] for m in generated_media), 4)
                if all(m.get("cost_usd") is not None for m in generated_media)
                else None
            ),
            "cost_status": (
                "reported" if all(m.get("cost_usd") is not None for m in generated_media)
                else "not_reported_by_provider"
            ),
            "scene_count": len(storyboard.scenes),
            "narration_file": narration_path,
            "background_music_file": background_music_path,
        },
    }

    from brain.planner import _apply_poster
    _apply_poster(plan, [])
    return plan


def export_post_image(job_id: str) -> Optional[str]:
    from app.jobs import get as get_job
    job = get_job(job_id)
    if not job:
        return None
    image_path = job.dir / "exports" / "post.png"
    if image_path.exists():
        return str(image_path)
    gen_dir = job.dir / "generated"
    provenance = gen_dir / "provenance.json"
    if not provenance.exists():
        return None
    media = json.loads(provenance.read_text())
    if not media:
        return None
    import shutil
    src = media[0]["file_path"]
    image_path.parent.mkdir(exist_ok=True)
    shutil.copy2(src, image_path)
    return str(image_path)
