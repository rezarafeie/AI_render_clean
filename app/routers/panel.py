"""Visual editor entry points. All media, plans and render jobs belong to Studio."""
import asyncio
import fcntl
import json
import os
import re
from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.routers import studio
from engine.operations import ResourceTransitionSettings
from engine.schema import CaptionStyle


router = APIRouter(prefix="/panel", tags=["manual-editor"])
repo = studio.repo
Modes = Literal["manual", "assisted", "auto"]
Engines = Literal["talking", "localize", "motion", "vox", "story", "product", "clips", "storyboard", "discovery"]


class StyleReference(BaseModel):
    model_config = {"extra": "forbid"}
    style_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    version: int = Field(ge=1, le=10000, strict=True)


class ProjectSetup(BaseModel):
    title: str = Field(default="پروژهٔ جدید", max_length=100)
    engine: Engines = "talking"
    mode: Modes = "manual"
    style: str = Field(default="", max_length=50)
    style_profile: StyleReference | None = None
    topic: str = Field(default="", max_length=1000)
    seconds: Literal[15, 30, 45, 60] = 30
    aspect: Literal["source", "vertical", "square", "landscape"] = "source"
    source_url: str = Field(default="", max_length=2000)
    motion_so: bool = False
    attachment_ids: list[str] = Field(default_factory=list, max_length=16)
    # The wizard's choices (each previewed before it is chosen); empty = the engine decides
    film_style: str = Field(default="", max_length=80)
    title_font: str = Field(default="", max_length=80)
    palette: list[str] = Field(default_factory=list, max_length=5)
    narrator: str = Field(default="", max_length=80)
    voice_style: str = Field(default="", max_length=30)
    music: str = Field(default="", max_length=200)


@contextmanager
def _lock(user: str, conversation: str):
    from app.studio_flags import conversation_dir

    directory = conversation_dir(user, conversation)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".manual-editor.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise HTTPException(409, "تغییر دیگری در حال ثبت است. دوباره امتحان کنید.") from exc
        yield


async def _owned(request: Request, conversation: str):
    user = studio._user(request)
    try:
        return user, await repo.get_conversation(conversation, user, message_limit=1)
    except KeyError as exc:
        raise HTTPException(404, "پروژه پیدا نشد.") from exc


def _motion_enabled():
    from creative import claude_motion
    return claude_motion.enabled()


_ASPECT_FA = {"vertical": "قطع عمودی ۹:۱۶", "square": "قطع مربع ۱:۱", "landscape": "قطع افقی ۱۶:۹"}


def _wizard_lines(setup: "ProjectSetup") -> list[str]:
    """The wizard's choices as lines the engines read: the director's brief (film style, title font, palette, format) and the production directives
    (Narrator:, Voice style:, Music:) that creative.directives applies exactly."""
    lines = []
    if setup.aspect in _ASPECT_FA:
        lines.append(_ASPECT_FA[setup.aspect])
    if setup.film_style:
        from creative import film_styles
        sid = film_styles.valid(setup.film_style)
        if sid:
            lines.append(f"سبک فیلم را از کتابخانهٔ سبک‌ها بگیر: {sid[5:]} (style id: {sid}).")
    if setup.title_font:
        from creative import font_catalog
        font = next((f for f in font_catalog.load() if f["id"] == setup.title_font), None)
        if font:
            lines.append(f"فونت تیتر: {font['label']} (font id: {font['id']}).")
    colours = [c for c in setup.palette if re.fullmatch(r"#[0-9A-Fa-f]{6}", c or "")]
    if colours:
        lines.append("پالت رنگ فیلم: " + "، ".join(colours) + " (رنگ اول زمینه، بقیه تأکید و متن).")
    if setup.narrator:
        lines.append(f"Narrator: {setup.narrator}")
    if setup.voice_style in {"calm", "serious", "energetic", "reflective", "natural"}:
        lines.append(f"Voice style: {setup.voice_style}")
    if setup.music == "off":
        lines.append("Music: off")
    elif setup.music.startswith("library:"):
        name = re.sub(r"\.[a-z0-9]{2,4}$", "", setup.music.split(":", 1)[1]).replace("_", " ").replace("-", " ").strip()
        if name:
            lines.append(f"Music: library {name}")
    return lines


_STYLE_CACHE: dict = {}


def _film_style_cards() -> list[dict]:
    """The 99 film styles for the wizard's gallery: id, a Persian name and one-line description, a 4-colour palette and a mood, written once by a model
    from each style's own text and kept on disk (job_data/panel_wizard/film_styles_fa.json); the English name until then."""
    from pathlib import Path
    from app.config import settings
    from creative import film_styles
    rows = sorted(film_styles._rows(), key=lambda r: r["id"])
    path = Path(settings.JOBS_DIR) / "panel_wizard" / "film_styles_fa.json"
    if not _STYLE_CACHE and path.is_file():
        try:
            _STYLE_CACHE.update(json.loads(path.read_text()))
        except ValueError:
            pass
    missing = [r for r in rows if r["id"] not in _STYLE_CACHE or not (_STYLE_CACHE.get(r["id"]) or {}).get("archetype")]
    if missing and not _STYLE_CACHE.get("_filling"):
        _STYLE_CACHE["_filling"] = True
        import threading

        def fill():
            try:
                from brain.llm import gateway_json
                for start in range(0, len(missing), 25):
                    batch = missing[start:start + 25]
                    text = "\n".join(f"{r['id']}: {(r.get('hint') or r.get('description') or '')[:220]}" for r in batch)
                    out, _ = gateway_json(
                        "For each film style below write a card for a Persian video app. Return JSON {\"styles\": [{\"id\": \"<exact id>\", \"title\": \"<2-4 word "
                        "Persian name>\", \"summary\": \"<one short Persian sentence: what the film looks and feels like>\", \"palette\": [\"#RRGGBB\" x4: background, "
                        "surface, accent, text - colours this style would really use], \"mood\": \"<one Persian word>\", \"motion\": \"slide|pop|drift|glitch|"
                        "draw|zoom\", \"archetype\": \"<the ONE scene that best shows this style: terminal|paper|blueprint|swiss|deco|bauhaus|newsreel|lighttable|"
                        "isometric|toy|anime|neon|data|map|cinema|minimal|riso|vhs|assembly|sketch>\"}]}.", text, "translation", 4000)
                    for item in (out or {}).get("styles", []):
                        if item.get("id") in {r["id"] for r in batch}:
                            _STYLE_CACHE[item["id"]] = {k: item.get(k) for k in ("title", "summary", "palette", "mood", "motion", "archetype")}
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({k: v for k, v in _STYLE_CACHE.items() if not k.startswith("_")}, ensure_ascii=False))
            except Exception:
                import logging
                logging.getLogger(__name__).warning("film style cards could not be written", exc_info=True)
            finally:
                _STYLE_CACHE.pop("_filling", None)
        threading.Thread(target=fill, daemon=True, name="film-style-cards").start()
    cards = []
    for r in rows:
        made = _STYLE_CACHE.get(r["id"]) or {}
        palette = [c for c in (made.get("palette") or []) if isinstance(c, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", c)][:4]
        cards.append({"id": r["id"][5:], "title": made.get("title") or r["name"].replace("-", " ").title(),
                      "summary": made.get("summary") or (r.get("hint") or "").split(":", 1)[0][:90], "palette": palette or ["#111318", "#1d2230", "#f2b84b", "#f5f1e8"],
                      "mood": made.get("mood") or "", "motion": made.get("motion") or "slide", "archetype": made.get("archetype") or ""})
    return cards


@router.get("/wizard/catalog")
async def wizard_catalog(request: Request):
    """Everything the wizard previews: film styles (with palettes), talking edit styles, narrators and delivery styles, the music library, palettes."""
    from engine.talking_reel import style_list
    from brain import localize
    try:
        from engine.library import library_for_api
        library = library_for_api()
        tracks = [a for a in (library.get("assets") or []) if isinstance(a, dict) and a.get("category") == "music"]
    except Exception:
        tracks = []
    music = [{"file": t.get("filename") or t.get("file") or t.get("name"), "label": (t.get("description") or t.get("filename") or "").replace("_", " ")[:60],
              "mood": t.get("mood") or "", "energy": t.get("energy")} for t in tracks if isinstance(t, dict)][:60]
    if not music:                                   # the bundled music beds (assets/music), the ones the engines pick from
        from app import talking_reel
        music = [{"file": t["path"].rsplit("/", 1)[-1], "label": t["label"], "mood": "", "energy": None} for t in talking_reel.music_library()]
    cards = await asyncio.to_thread(_film_style_cards)
    return {"film_styles": cards, "talking_styles": style_list(),
            "voices": [{"id": i, "name": n, "note": d} for i, n, d in localize.NARRATORS if i],
            "voice_styles": [{"id": k or "natural", "label": v[0]} for k, v in localize.VOICE_STYLES.items()],
            "music": [m for m in music if m["file"]],
            "palettes": [{"name": "شب و طلا", "colors": ["#0f1115", "#1b1f2a", "#f2b84b", "#f6f1e7"]},
                         {"name": "کاغذ و جوهر", "colors": ["#f3ecdf", "#e4d8c3", "#c0392b", "#1d1d1d"]},
                         {"name": "نئون شب", "colors": ["#0b0b14", "#16162a", "#ff3d81", "#e8f0ff"]},
                         {"name": "طبیعت آرام", "colors": ["#eef2ea", "#d6e2cf", "#2f7d5b", "#1e2a24"]},
                         {"name": "اقیانوس", "colors": ["#0a1a2a", "#12304a", "#3fc1ff", "#eaf6ff"]},
                         {"name": "مینیمال سفید", "colors": ["#ffffff", "#f1f1f1", "#2d6cdf", "#111111"]}]}


@router.get("/wizard/music/{name}")
async def wizard_music(name: str):
    """A music bed to play in the wizard (the library's own files only)."""
    from pathlib import Path
    from fastapi.responses import FileResponse
    from app import talking_reel
    from engine.library import LIBRARY_ROOT
    if not re.fullmatch(r"[\w .()-]{1,120}\.(mp3|wav|m4a)", name):
        raise HTTPException(404, "track not found")
    for folder in (LIBRARY_ROOT / "music", Path(talking_reel.PROJECT_ROOT) / "assets" / "music"):
        path = folder / name
        if path.is_file():
            return FileResponse(path, media_type="audio/mpeg")
    raise HTTPException(404, "track not found")


class TitleIdea(BaseModel):
    text: str = Field(min_length=2, max_length=1200)


@router.post("/wizard/title")
async def wizard_title(request: Request, body: TitleIdea):
    """A short project name suggested from what the person wrote (the same title writer the chats use)."""
    from app.studio_title import make_title
    return {"title": (await asyncio.to_thread(make_title, body.text))[:100]}


@router.get("/capabilities")
async def capabilities():
    from brain import motion_so
    from engine.talking_reel import style_list
    return {"talking_styles": style_list(), "claude_motion": _motion_enabled(), "motion_so": motion_so.configured()}


class PanelPreferences(BaseModel):
    model_config = {"extra": "forbid"}
    mode: Modes | None = None
    agent_mode: Literal["lite", "medium", "pro"] | None = None


def _preferences_path(user: str, conversation: str):
    from app.studio_flags import conversation_dir

    return conversation_dir(user, conversation) / "panel-preferences.json"


def _read_panel_preferences(path) -> PanelPreferences:
    try:
        return PanelPreferences.model_validate_json(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return PanelPreferences()


@router.get("/{conversation}/preferences")
async def get_preferences(request: Request, conversation: str):
    user, _ = await _owned(request, conversation)
    return await asyncio.to_thread(_read_panel_preferences, _preferences_path(user, conversation))


@router.patch("/{conversation}/preferences")
async def save_preferences(request: Request, conversation: str, body: PanelPreferences):
    user, _ = await _owned(request, conversation)
    with _lock(user, conversation):
        path = _preferences_path(user, conversation)
        prior = _read_panel_preferences(path)
        updated = prior.model_copy(update=body.model_dump(exclude_unset=True))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(updated.model_dump(), ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return updated


@router.post("/draft", status_code=201)
async def draft(request: Request):
    chat = await studio.create_conversation(request, studio.ConversationCreate(title="پروژهٔ دستی جدید"))
    state = {**chat["state"], "panel": {"setup": ProjectSetup().model_dump()}}
    return studio._public_conversation(await repo.set_conversation(chat["id"], studio._user(request), state=state))


@router.put("/{conversation}/setup")
async def save_setup(request: Request, conversation: str, setup: ProjectSetup):
    user, chat = await _owned(request, conversation)
    with _lock(user, conversation):
        _, chat = await _owned(request, conversation)
        panel = chat["state"].get("panel")
        if panel is None or chat["projects"] or (chat["state"].get("motion") or chat["state"].get("discovery")):
            raise HTTPException(409, "پیکربندی منبع فقط برای پیش‌نویس جدید قابل تغییر است.")
        try:
            await repo.get_attachments(setup.attachment_ids, conversation, user)
        except KeyError as exc:
            raise HTTPException(404, "یکی از فایل‌ها در همین پروژه پیدا نشد.") from exc
        state = {**chat["state"], "panel": {**panel, "setup": setup.model_dump()}}
        return studio._public_conversation(await repo.set_conversation(
            conversation, user, state=state, title=setup.title.strip() or "پروژهٔ دستی جدید"))


@router.get("/{conversation}/media")
async def draft_media(request: Request, conversation: str):
    user, chat = await _owned(request, conversation)
    ids = ((chat["state"].get("panel") or {}).get("setup") or {}).get("attachment_ids") or []
    try:
        attachments = await repo.get_attachments(ids, conversation, user)
    except KeyError as exc:
        raise HTTPException(409, "یک فایل انتخاب‌شده دیگر در دسترس نیست.") from exc
    return [{key: item[key] for key in ("id", "filename", "kind", "mime_type", "size_bytes")} for item in attachments]


class MotionAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)


@router.post("/{conversation}/motion/answer")
async def answer_motion(request: Request, conversation: str, body: MotionAnswer):
    from app import credits, motion_graphic
    user, _ = await _owned(request, conversation)
    with _lock(user, conversation):
        _, chat = await _owned(request, conversation)
        motion_id = (chat["state"].get("motion") or {}).get("motion_id")
        if not motion_id:
            raise HTTPException(404, "موشن پروژه پیدا نشد.")
        directory = studio._motion_dir(request, motion_id)
        record = await asyncio.to_thread(motion_graphic.load, directory)
        if record["status"] != "needs_input":
            raise HTTPException(409, "موتور دیگر منتظر پاسخ نیست.")
        if not body.answer.strip():
            raise HTTPException(422, "پاسخ را وارد کنید.")
        await credits.gate(user)
        await asyncio.to_thread(motion_graphic.answer, directory, body.answer)
    return {"ok": True}


_MOTION_BRIEFS = {
    "motion": "یک موشن‌گرافیک توضیحی بساز.",
    "vox": "یک ویدیوی توضیحی مستند به سبک ووکس بساز.",
    "story": "ویدیوی معرفی به سبک قصه بساز.",
    "product": "ویدیوی معرفی محصول به شکل شوریل بساز.",
}


def _create_clip_job(user: str, source: dict, aspect: str, style: StyleReference | None = None):
    """Seed a plain native EditPlan from a validated Studio source."""
    from fractions import Fraction
    from pathlib import Path

    from app import jobs
    from engine.probe import probe

    path = Path(source["path"])
    metadata = probe(path)
    stream = next((row for row in metadata.get("streams", []) if row.get("codec_type") == "video"), None)
    duration = float(metadata.get("format", {}).get("duration") or 0)
    if not stream or duration <= 0:
        raise ValueError("فایل ویدیوی قابل برش ندارد.")
    try:
        fps = round(float(Fraction(stream.get("avg_frame_rate") or "30")))
    except (ZeroDivisionError, ValueError):
        fps = 30
    fps = max(1, min(120, fps or 30))
    if duration < 1 / fps:
        raise ValueError("ویدیو از یک فریم کوتاه‌تر است.")
    width, height = int(stream["width"]), int(stream["height"])
    side_data = stream.get("side_data_list") or []
    rotations = [row.get("rotation") for row in side_data if "rotation" in row]
    rotation = int(rotations[0]) if rotations else int((stream.get("tags") or {}).get("rotate", 0))
    if abs(rotation) % 180 == 90:
        width, height = height, width
    presets = {"vertical": (1080, 1920), "square": (1080, 1080), "landscape": (1920, 1080)}
    width, height = presets.get(aspect, (width // 2 * 2, height // 2 * 2))
    if min(width, height) < 2 or max(width, height) > 4096:
        raise ValueError("برای این ویدیو یکی از ابعاد استاندارد را انتخاب کنید.")
    selection = None
    if style:
        from engine.style_library import list_library, resolve_preset

        profile = next((row for row in list_library()["profiles"]
                        if row.get("state") == "approved" and row["style_id"] == style.style_id and row["version"] == style.version), None)
        if not profile:
            raise HTTPException(422, "این نسخهٔ سبک دیگر برای پروژهٔ جدید در دسترس نیست.")
        try:
            resolve_preset(style.style_id, style.version)
        except (KeyError, ValueError) as exc:
            raise HTTPException(422, "نسخهٔ سبک با موتور تدوین سازگار نیست.") from exc
        selection = {**style.model_dump(), "name": profile["name"], "state": "pinned"}
    job = jobs.create_job(user_id=user)
    try:
        with path.open("rb") as media:
            raw = jobs.save_raw(job, source["filename"], media, expected_size=source["size_bytes"])
        plan = {"source": raw.relative_to(job.dir).as_posix(),
                "canvas": {"width": width, "height": height, "fps": fps},
                "segments": [{"id": "clip-1", "in": 0.0, "out": duration}],
                "export": {"file": "manual-edit.mp4"}}
        _, errors = jobs.save_plan(job, plan)
        if errors:
            raise ValueError("برنامهٔ اولیه با فرمت این ویدیو سازگار نیست.")
        if selection:
            (job.dir / "style_selection.json").write_text(json.dumps(selection, ensure_ascii=False), encoding="utf-8")
    except Exception:
        jobs.delete_job(job.id)
        raise
    return job.id


@router.post("/{conversation}/start", status_code=202)
async def start(request: Request, conversation: str):
    from app import credits
    from app.studio_tools import execute
    from brain.lm_gateway import work_scope

    user, _ = await _owned(request, conversation)
    with _lock(user, conversation):
        _, chat = await _owned(request, conversation)
        if chat["projects"] or (chat["state"].get("motion") or chat["state"].get("discovery")):
            return {"id": conversation, "started": True}
        panel = chat["state"].get("panel")
        if not panel:
            raise HTTPException(409, "این پروژه از صفحهٔ ادیتور دستی ساخته نشده است.")
        setup = ProjectSetup.model_validate(panel["setup"])
        try:
            attachments = await repo.get_attachments(setup.attachment_ids, conversation, user)
        except KeyError as exc:
            raise HTTPException(404, "یکی از فایل‌ها پیدا نشد.") from exc
        source = next((item for item in attachments if item["kind"] == "video"), None)
        if setup.engine in ("talking", "localize", "clips", "discovery") and not source:
            raise HTTPException(422, "یک فایل ویدیو انتخاب کنید.")
        if setup.engine in ("vox", "story", "product") and not _motion_enabled():
            raise HTTPException(409, "موتور طراحی این سبک روی سرور فعال نیست.")
        allowed_sources = {"video", "image"} if setup.engine == "storyboard" else {"video", "image", "audio"}
        if (setup.engine in _MOTION_BRIEFS or setup.engine == "storyboard") and not (
            setup.topic.strip() or setup.source_url or any(item["kind"] in allowed_sources for item in attachments)
        ):
            raise HTTPException(422, "موضوع، لینک منبع یا فایل مرتبط را وارد کنید.")
        if setup.engine == "storyboard":
            from brain import motion_so
            source_text = f"{setup.topic} {setup.source_url}".lower()
            if ("motion.so" in source_text or "کلیپ موشن هوشمند" in source_text) and not setup.motion_so:
                raise HTTPException(422, "برای این درخواست، گزینهٔ Motion.so را فعال کنید.")
            if setup.motion_so and not motion_so.configured():
                raise HTTPException(409, "سرویس Motion.so روی این نصب فعال نیست.")
        if setup.source_url:
            from urllib.parse import urlsplit
            try:
                url = urlsplit(setup.source_url)
                if url.scheme not in ("http", "https") or not url.hostname or url.username is not None:
                    raise ValueError
            except ValueError as exc:
                raise HTTPException(422, "آدرس وب معتبر نیست.") from exc

        from engine.talking_reel import style_list
        style = setup.style or None
        if setup.engine == "talking" and style not in {None, "premium", *(item["id"] for item in style_list())}:
            raise HTTPException(422, "سبک انتخاب‌شده برای پروژهٔ جدید در دسترس نیست.")

        if setup.engine != "clips":
            await credits.gate(user)
        with work_scope("manual_editor", conversation, user=user, conversation=conversation):
            if setup.engine in _MOTION_BRIEFS:
                from app.studio_orchestrator import _start_motion_graphic
                brief = "\n".join(filter(None, [_MOTION_BRIEFS[setup.engine], setup.topic.strip(),
                                               f"مدت حدود {setup.seconds} ثانیه", setup.source_url, *_wizard_lines(setup)]))
                await asyncio.to_thread(_start_motion_graphic, conversation, user, chat, brief, attachments)
                _, updated = await _owned(request, conversation)
                if not updated["state"].get("motion"):
                    raise HTTPException(422, "منبع برای ساخت موشن قابل استفاده نبود.")
            elif setup.engine == "storyboard":
                from app.studio_orchestrator import _create_motion
                brief = "\n".join(filter(None, ["یک ویدیوی تصویری با استوری‌بورد قابل‌ویرایش بساز.",
                                               setup.topic.strip(), f"مدت حدود {setup.seconds} ثانیه",
                                               "Motion.so" if setup.motion_so else "", setup.source_url, *_wizard_lines(setup)]))
                try:
                    await asyncio.to_thread(_create_motion, conversation, user, f"panel:{conversation}", brief, attachments)
                except ValueError as exc:
                    raise HTTPException(422, "موتور نتوانست از ورودی، استوری‌بورد قابل تأیید بسازد.") from exc
                _, updated = await _owned(request, conversation)
                if not updated["projects"]:
                    raise HTTPException(422, "منبع برای ساخت استوری‌بورد قابل استفاده نبود.")
            elif setup.engine == "discovery":
                from app.studio_orchestrator import _start_discovery
                focus = setup.topic.strip() or "بخش‌های مستقل و قابل انتشار این ویدیوی بلند را پیدا کن."
                await asyncio.to_thread(_start_discovery, conversation, user, chat, attachments, focus)
            elif setup.engine == "clips":
                from app import jobs
                try:
                    ref = await asyncio.to_thread(_create_clip_job, user, source, setup.aspect, setup.style_profile)
                except (ValueError, OSError) as exc:
                    raise HTTPException(422, "آماده‌سازی ویدیو برای برش انجام نشد.") from exc
                state = {"attachment_ids": [source["id"]], "panel_native": True, "confirmed": False,
                         "render_target": "server", "last_observed": {}}
                try:
                    project = await repo.create_project(conversation, user, "motion",
                        setup.title.strip() or source["filename"], state, ref)
                except Exception:
                    await asyncio.to_thread(jobs.delete_job, ref)
                    raise
                await repo.update_project(project["id"], user, status="awaiting_confirmation")
            else:
                payload = {"source_path": source["path"], "filename": source["filename"], "user_key": user}
                ordered = [source["id"], *(row["id"] for row in attachments if row["id"] != source["id"])]
                state = {"attachment_ids": ordered, "auto_render": False,
                         "last_observed": {}, "render_target": "server", "panel_created": True}
                if setup.engine == "talking":
                    payload.update(style=None if style == "premium" else style,
                                   variant="premium" if style == "premium" else None)
                    state.update(workflow="analyzing", selected_style=None if style == "premium" else style)
                result = await asyncio.to_thread(execute, "analyze_talking_reel" if setup.engine == "talking" else "localize_video", payload)
                project = await repo.create_project(conversation, user, setup.engine,
                    setup.title.strip() or source["filename"], state, result["external_ref"])
                await repo.update_project(project["id"], user, status="running")
                await repo.emit(conversation, "tool.started", {"project_id": project["id"], "message": "تحلیل ویدیو شروع شد."})
    return {"id": conversation, "started": True}


async def _transcript_job(request, project_id):
    from app import jobs
    user = studio._user(request)
    try:
        project = await repo.get_project(project_id, user)
    except KeyError as exc:
        raise HTTPException(404, "پروژه پیدا نشد.") from exc
    job = jobs.get(project.get("external_ref")) if project["engine"] == "talking" and project.get("external_ref") else None
    if not job or not (job.dir / "transcript.json").is_file():
        raise HTTPException(409, "متن گفتار پس از تحلیل ویدیوی صحبتی در دسترس است.")
    return user, project, job


@router.get("/projects/{project_id}/transcript")
async def transcript(request: Request, project_id: str):
    from app import talking_reel
    from app.creative_plan import current

    _, project, job = await _transcript_job(request, project_id)
    raw = await asyncio.to_thread(talking_reel.transcript_for, job.dir, job.dir / "raw" / job.raw_name)
    engine = talking_reel.load(job.dir)
    settings = engine.get("render_settings") or {}
    dropped = set(settings.get("dropped_sentences") or [])
    version = current(project["state"])
    words = raw.get("words") or []
    from bisect import bisect_left
    starts = [word["start"] for word in words]
    return {
        "source_job": job.id, "version_id": (version or {}).get("id"),
        "editable": engine.get("style") == "talking_1" and engine.get("variant") != "premium"
                    and not settings.get("captions_only") and bool(version)
                    and project["state"].get("workflow") not in {"analyzing", "production"},
        "sentences": [{"id": index, "start": row["start"], "end": row["end"], "text": row["text"],
                       "dropped": index in dropped,
                       "words": [{"text": word.get("w", word.get("text", "")), "start": word["start"], "end": word["end"]}
                                 for word in words[bisect_left(starts, row["start"]):bisect_left(starts, row["end"])]]}
                      for index, row in enumerate(raw.get("sentences") or [])],
    }


class SentenceCut(BaseModel):
    version_id: str = Field(min_length=8, max_length=64)
    sentence: int = Field(ge=0, lt=10000)
    remove: bool


@router.patch("/projects/{project_id}/transcript")
async def cut_sentence(request: Request, project_id: str, edit: SentenceCut):
    from app import creative_plan, talking_reel
    from app.studio_orchestrator import _refresh_plan
    from creative.revise import RevisionOp, apply_to_talking

    user, project, _ = await _transcript_job(request, project_id)
    with _lock(user, project["conversation_id"]):
        _, project, job = await _transcript_job(request, project_id)
        version = creative_plan.current(project["state"])
        state = talking_reel.load(job.dir)
        if not version or version["id"] != edit.version_id:
            raise HTTPException(409, "برنامه تغییر کرده است. دوباره بارگذاری کنید.")
        if (project["state"].get("workflow") in {"analyzing", "production"}
            or state.get("style") != "talking_1" or state.get("variant") == "premium"
            or (state.get("render_settings") or {}).get("captions_only")):
            raise HTTPException(409, "برش جمله در این سبک یا هنگام رندر در دسترس نیست.")
        raw = await asyncio.to_thread(talking_reel.transcript_for, job.dir, job.dir / "raw" / job.raw_name)
        count = len(raw.get("sentences") or [])
        if edit.sentence >= count:
            raise HTTPException(422, "جمله پیدا نشد.")
        settings = state.get("render_settings") or {}
        dropped = set(settings.get("dropped_sentences") or [])
        if (edit.sentence in dropped) == edit.remove:
            return {"ok": True}
        if edit.remove:
            if len(dropped | {edit.sentence}) >= count:
                raise HTTPException(422, "حداقل یک جمله باید در تدوین باقی بماند.")
            change = apply_to_talking(talking_reel.public(state), [RevisionOp(op="remove_sentence", sentence=edit.sentence)], count)
            changes = change.changes
        else:
            changes = {"render_settings": {**settings, "dropped_sentences": sorted(dropped - {edit.sentence})}}
        if not changes:
            raise HTTPException(409, "موتور این تغییر را نپذیرفت.")
        await asyncio.to_thread(talking_reel.update, job.dir, changes)
        try:
            await asyncio.to_thread(talking_reel.plan_render, job.dir, job.dir / "raw" / job.raw_name,
                                    prepare_media=False)
        except ValueError as exc:
            await asyncio.to_thread(talking_reel.update, job.dir, {"render_settings": settings})
            raise HTTPException(422, "این برش محتوای قابل رندر باقی نمی‌گذارد.") from exc
        try:
            refreshed, _ = await _refresh_plan(project["conversation_id"], user, project, job, source="manual",
                                               note="برش گفتار از ادیتور دستی", announce=False, after_analysis=True)
            latest = creative_plan.current(refreshed["state"])
            content = {**latest["content"], "speech_cuts": changes["render_settings"]["dropped_sentences"]}
            next_state, created = creative_plan.add_version(refreshed["state"], content, source="manual", note="برش گفتار از ادیتور دستی")
            if created:
                await repo.update_project(project_id, user, state=next_state, status="awaiting_confirmation", source="manual")
        except Exception:
            await asyncio.to_thread(talking_reel.update, job.dir, {"render_settings": settings})
            raise
    return {"ok": True}


async def _native_job(request, project_id):
    from app import jobs

    user = studio._user(request)
    try:
        project = await repo.get_project(project_id, user)
    except KeyError as exc:
        raise HTTPException(404, "پروژه پیدا نشد.") from exc
    ref = project.get("external_ref")
    job = jobs.get(ref) if project["engine"] == "motion" and ref else None
    if not job or (job.user_id is not None and str(job.user_id) != user):
        raise HTTPException(409, "این پروژه برنامهٔ تدوین بومی ندارد.")
    try:
        plan = await asyncio.to_thread(jobs.load_plan, job)
    except FileNotFoundError as exc:
        raise HTTPException(409, "برنامهٔ تدوین هنوز آماده نیست.") from exc
    if (plan.get("generation_meta") or {}).get("remotion") or not plan.get("segments"):
        raise HTTPException(409, "این خروجی از یک کامپوزیشن تولید شده و برش بومی برایش در دسترس نیست.")
    return job, plan


@router.get("/projects/{project_id}/segments")
async def native_segments(request: Request, project_id: str):
    from app import plan_versions
    from engine.operations import segment_spans

    job, plan = await _native_job(request, project_id)
    spans = segment_spans(plan)
    versions = await asyncio.to_thread(plan_versions.list_versions, job)
    effects = {item["segment_id"]: item["type"] for item in plan.get("visual_effects") or []}
    incoming = {item["to_segment_id"]: item for item in plan.get("transitions") or []}
    transitioned = set(incoming) | {item["from_segment_id"] for item in incoming.values()}
    def span_payload(span):
        row = plan["segments"][span.index]
        zoom = row.get("zoom") or {"from": 1.0, "to": 1.0}
        return {"id": span.id, "start": span.start, "end": span.end,
                "source_in": span.source_in, "source_out": span.source_out, "zoom": zoom,
                "effect": effects.get(span.id),
                "transition": ({"type": incoming[span.id]["type"], "frames": incoming[span.id]["duration_frames"]}
                               if span.id in incoming else None),
                "zoom_editable": span.id not in effects,
                "splittable": span.id not in effects and span.id not in transitioned and zoom["from"] == zoom["to"]}
    from pathlib import Path
    layers = []
    for kind, key in _LAYER_KEYS.items():
        rows = [plan[key]] if kind == "music" and plan.get(key) else plan.get(key) or []
        for index, row in enumerate(rows):
            start = row.get("start", row.get("at", 0))
            end = row.get("end", start + row.get("duration", 0))
            path = Path(row.get("file") or "")
            attachment_id = path.parts[2] if len(path.parts) == 4 and path.parts[0] == "assets" and path.parts[1] in {"panel-media", "panel-stills"} else None
            still = _STILL_ASSET.fullmatch(path.name) if attachment_id and path.parts[1] == "panel-stills" else None
            layers.append({"kind": kind, "index": index, "start": start,
                           "end": spans[-1].end if kind == "music" else end,
                           "label": row.get("text") or (still["name"] if still else path.name), "attachment_id": attachment_id,
                           "attachment_kind": ("image" if still else ("video" if kind == "broll" else "audio")) if attachment_id else None,
                           "source_in": row.get("in", 0), "caption_style": row.get("style", "normal"),
                           "highlight": row.get("highlighted_word") or "",
                           "position": row.get("position", "bottom"), "volume_db": row.get("volume_db", -14)})
    return {"segments": [span_payload(span) for span in spans], "duration": spans[-1].end,
            "layers": layers,
            "caption_font": plan["canvas"].get("caption_font"),
            "caption_font_id": plan["canvas"].get("caption_font_id"),
            "width": plan["canvas"].get("width"), "height": plan["canvas"].get("height"),
            "crf": (plan.get("export") or {}).get("crf", 20),
            "arrange": _can_arrange(plan),
            "fps": plan["canvas"]["fps"], "job_id": job.id,
            "version": versions[-1]["version"] if versions else None,
            "versions": [{"version": row["version"], "source": row.get("source", "")} for row in versions],
            "busy": job.render.status in {"queued", "running"}}


class SegmentChange(BaseModel):
    model_config = {"extra": "forbid"}
    version: int | None = None
    operation: Literal["trim", "remove_range", "restore", "split", "duplicate", "move", "zoom", "paste"]
    segment_id: str | None = Field(default=None, max_length=80)
    start: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    end: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    restore_version: int | None = Field(default=None, ge=1)
    target_id: str | None = Field(default=None, max_length=80)
    after: bool = False
    zoom_from: float | None = Field(default=None, ge=1.0, le=1.5, allow_inf_nan=False)
    zoom_to: float | None = Field(default=None, ge=1.0, le=1.5, allow_inf_nan=False)


def _can_arrange(plan: dict) -> bool:
    # Current EditPlan geometry cannot remap every overlay through a reorder.
    return not any(plan.get(key) for key in (
        "captions", "broll", "music", "sfx", "visual_effects", "transitions", "poster", "cover", "denoise", "generation_meta",
    ))


def _arrange_segments(plan: dict, body: SegmentChange) -> dict:
    from copy import deepcopy
    from uuid import uuid4

    if body.operation in {"duplicate", "move", "paste"} and not _can_arrange(plan):
        raise HTTPException(409, "این برنامه لایه‌هایی دارد که با جابه‌جایی قطعه همگام نمی‌شوند.")
    result = deepcopy(plan)
    clips = result["segments"]
    index = next((i for i, row in enumerate(clips) if row["id"] == body.segment_id), None)
    if index is None:
        raise HTTPException(422, "قطعه پیدا نشد.")
    clip = clips[index]
    if body.operation in {"duplicate", "split", "paste"} and len(clips) >= 500:
        raise HTTPException(422, "سقف تعداد قطعه‌های این برنامه رسیده است.")
    if body.operation == "duplicate":
        clips.insert(index + 1, {**clip, "id": "clip-" + uuid4().hex[:12]})
    elif body.operation == "paste":
        fps = plan["canvas"]["fps"]
        if (body.start is None or body.end is None or round((body.end - body.start) * fps) < 1
                or body.zoom_from is None or body.zoom_to is None):
            raise HTTPException(422, "قطعهٔ کپی‌شده بازهٔ معتبر ندارد.")
        clips.insert(index + 1, {"id": "clip-" + uuid4().hex[:12], "in": body.start, "out": body.end,
                                 "zoom": {"from": body.zoom_from, "to": body.zoom_to}})
    elif body.operation == "zoom":
        if any(row["segment_id"] == clip["id"] for row in plan.get("visual_effects") or []):
            raise HTTPException(409, "افکت این قطعه، حرکت دوربین را تعیین می‌کند.")
        if body.zoom_from is None or body.zoom_to is None:
            raise HTTPException(422, "مقدار آغاز و پایان زوم را وارد کنید.")
        clip["zoom"] = {"from": body.zoom_from, "to": body.zoom_to}
    elif body.operation == "split":
        zoom = clip.get("zoom") or {"from": 1.0, "to": 1.0}
        if (zoom["from"] != zoom["to"]
                or any(row["segment_id"] == clip["id"] for row in plan.get("visual_effects") or [])
                or any(clip["id"] in (row["from_segment_id"], row["to_segment_id"])
                       for row in plan.get("transitions") or [])):
            raise HTTPException(409, "تقسیم این قطعه زمان‌بندی افکت، زوم یا ترنزیشن آن را تغییر می‌دهد.")
        if body.start is None:
            raise HTTPException(422, "زمان برش را انتخاب کنید.")
        frame = 1 / plan["canvas"]["fps"]
        start, end = clip["in"], clip["out"]
        cut_frames = round((body.start - start) / frame)
        total_frames = round((end - start) / frame)
        if cut_frames < 1 or cut_frames >= total_frames:
            raise HTTPException(422, "در هر طرف برش دست‌کم یک فریم لازم است.")
        cut = start + cut_frames * frame
        if cut >= end:
            raise HTTPException(422, "زمان تقسیم باید داخل قطعه باشد.")
        # Snap relative to the source in-point so the two rendered frame
        # counts sum to the original and output-timed layers stay aligned.
        clips[index:index + 1] = [{**clip, "out": cut},
                                  {**clip, "id": "clip-" + uuid4().hex[:12], "in": cut}]
    else:
        if body.target_id == body.segment_id:
            return plan
        clips.pop(index)
        target = next((i for i, row in enumerate(clips) if row["id"] == body.target_id), None)
        if target is None:
            raise HTTPException(422, "مقصد جابه‌جایی پیدا نشد.")
        clips.insert(target + int(body.after), clip)
    return result


@router.patch("/projects/{project_id}/segments")
async def change_segment(request: Request, project_id: str, body: SegmentChange):
    from app import jobs, plan_versions

    if body.operation == "trim":
        operation = {"op": "trim_segment", "segment_id": body.segment_id,
                     "source_in": body.start, "source_out": body.end}
    else:
        operation = {"op": "remove_range", "t_start": body.start, "t_end": body.end}
    if body.operation in {"trim", "remove_range"} and (body.start is None or body.end is None or body.start >= body.end):
        raise HTTPException(422, "ابتدا یک بازهٔ زمانی معتبر انتخاب کنید.")
    user = studio._user(request)
    await _native_job(request, project_id)
    with _lock(user, project_id):
        job, plan = await _native_job(request, project_id)
        try:
            latest = await asyncio.to_thread(plan_versions.latest_version, job)
            if (latest["version"] if latest else None) != body.version or job.render.status in {"queued", "running"}:
                raise HTTPException(409, "برنامه تغییر کرده یا در حال رندر است.")
            if body.operation == "restore":
                if body.restore_version is None:
                    raise HTTPException(422, "نسخهٔ برنامه را انتخاب کنید.")
                prior = await asyncio.to_thread(plan_versions.get_version, job, body.restore_version)
                if not prior:
                    raise HTTPException(404, "این نسخهٔ برنامه پیدا نشد.")
                _, errors = await asyncio.to_thread(jobs.save_plan, job, prior["plan"], source="user_ui",
                    operations=[{"op": "restore", "from_version": body.restore_version}])
                if errors:
                    raise HTTPException(422, "بعضی از رسانه‌های این نسخه در دسترس نیستند.")
            elif body.operation in {"split", "duplicate", "move", "zoom", "paste"}:
                candidate = _arrange_segments(plan, body)
                if candidate != plan:
                    _, errors = await asyncio.to_thread(jobs.save_plan, job, candidate, source="user_ui",
                        operations=[{"op": body.operation, "segment_id": body.segment_id}])
                    if errors:
                        raise HTTPException(422, "تغییر قطعه با برنامهٔ رندر سازگار نیست.")
            else:
                await asyncio.to_thread(jobs.apply_plan_operations, job, [operation],
                                        base_version=body.version, base_plan=plan)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    return await native_segments(request, project_id)


class NativeResourceChange(BaseModel):
    model_config = {"extra": "forbid"}
    version: int | None = None
    kind: Literal["effect", "transition"]
    resource_id: str = Field(min_length=1, max_length=160)
    targets: list[str] = Field(min_length=1, max_length=500)
    settings: ResourceTransitionSettings = Field(default_factory=ResourceTransitionSettings)


@router.patch("/projects/{project_id}/resource")
async def apply_native_resource(request: Request, project_id: str, body: NativeResourceChange):
    from app import jobs, plan_versions

    user = studio._user(request)
    await _native_job(request, project_id)
    with _lock(user, project_id):
        job, plan = await _native_job(request, project_id)
        latest = await asyncio.to_thread(plan_versions.latest_version, job)
        if (latest["version"] if latest else None) != body.version or job.render.status in {"queued", "running"}:
            raise HTTPException(409, "برنامه تغییر کرده یا در حال رندر است.")
        ids = [row["id"] for row in plan["segments"]]
        neighbors = dict(zip(ids, ids[1:]))
        operations = []
        for target in dict.fromkeys(body.targets):
            if body.kind == "effect" and target in ids:
                operations.extend([
                    {"op": "set_resource_effect", "segment_id": target, "resource_id": body.resource_id},
                    {"op": "lock", "target": "effect", "segment_id": target},
                ])
            elif body.kind == "transition" and target in neighbors:
                operations.append({"op": "set_resource_transition", "from_segment_id": target,
                                   "to_segment_id": neighbors[target], "resource_id": body.resource_id,
                                   "settings": body.settings.model_dump()})
            else:
                raise HTTPException(422, "قطعه یا اتصال در برنامهٔ ذخیره‌شده پیدا نشد.")
        try:
            await asyncio.to_thread(jobs.apply_plan_operations, job, operations,
                                    base_version=body.version, base_plan=plan)
        except jobs.PlanVersionConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    return await native_segments(request, project_id)


class NativeExportChange(BaseModel):
    model_config = {"extra": "forbid"}
    version: int | None = None
    width: int = Field(ge=2, le=4096, multiple_of=2, strict=True)
    height: int = Field(ge=2, le=4096, multiple_of=2, strict=True)
    crf: int = Field(ge=0, le=51, strict=True)


@router.patch("/projects/{project_id}/export")
async def set_native_export(request: Request, project_id: str, body: NativeExportChange):
    from app import jobs, plan_versions

    user = studio._user(request)
    await _native_job(request, project_id)
    with _lock(user, project_id):
        job, plan = await _native_job(request, project_id)
        project = await repo.get_project(project_id, user)
        if not project["state"].get("panel_native"):
            raise HTTPException(409, "اندازهٔ خروجی برای این موتور در تنظیمات خودش تعیین می‌شود.")
        latest = await asyncio.to_thread(plan_versions.latest_version, job)
        if (latest["version"] if latest else None) != body.version or job.render.status in {"queued", "running"}:
            raise HTTPException(409, "برنامه تغییر کرده یا در حال رندر است.")
        candidate = {**plan,
                     "canvas": {**plan["canvas"], "width": body.width, "height": body.height},
                     "export": {**plan["export"], "crf": body.crf}}
        if candidate != plan:
            _, errors = await asyncio.to_thread(jobs.save_plan, job, candidate, source="user_ui",
                                               operations=[{"op": "export_settings", **body.model_dump(exclude={"version"})}])
            if errors:
                raise HTTPException(422, "اندازه یا کیفیت خروجی با برنامهٔ رندر سازگار نیست.")
    return await native_segments(request, project_id)


class NativeRender(BaseModel):
    version: int | None = None
    preview: bool = False


@router.post("/projects/{project_id}/segments/render", status_code=202)
async def render_segments(request: Request, project_id: str, body: NativeRender):
    from app import jobs, plan_versions

    user = studio._user(request)
    await _native_job(request, project_id)
    with _lock(user, project_id):
        job, plan = await _native_job(request, project_id)
        project = await repo.get_project(project_id, user)
        if project["state"].get("render_target") == "browser":
            raise HTTPException(409, "این پروژه برای رندر مرورگر تنظیم شده است.")
        latest = await asyncio.to_thread(plan_versions.latest_version, job)
        if (latest["version"] if latest else None) != body.version:
            raise HTTPException(409, "از آخرین نسخهٔ برنامه رندر بگیرید.")
        try:
            await asyncio.to_thread(jobs.start_render, job, preview=body.preview, loudnorm=not body.preview, expected_plan=plan)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(409, str(exc)) from exc
        if project["state"].get("panel_native"):
            state = {**project["state"], "confirmed": True, "last_observed": {}}
            await repo.update_project(project_id, user, state=state, status="running")
    return {"status": job.render.status}


class LayerChange(BaseModel):
    model_config = {"extra": "forbid"}
    version: int | None = None
    kind: Literal["caption", "broll", "music", "sfx"]
    operation: Literal["add", "remove", "replace"]
    index: int | None = Field(default=None, ge=0, lt=1000)
    text: str = Field(default="", max_length=400)
    filename: str = Field(default="", max_length=255)
    attachment_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    source_in: float = Field(default=0, ge=0, allow_inf_nan=False)
    caption_style: CaptionStyle | None = None
    highlight: str | None = Field(default=None, max_length=80)
    start: float = Field(default=0, ge=0, allow_inf_nan=False)
    end: float = Field(default=0, ge=0, allow_inf_nan=False)
    volume_db: float = Field(default=-14, ge=-80, le=12, allow_inf_nan=False)
    position: Literal["top", "bottom"] = "bottom"


_LAYER_KEYS = {"caption": "captions", "broll": "broll", "music": "music", "sfx": "sfx"}


def _library_file(kind: str, filename: str):
    from pathlib import Path
    from engine.library import LIBRARY_ROOT, load_index

    if not filename or Path(filename).name != filename:
        raise HTTPException(422, "یک فایل کتابخانه انتخاب کنید.")
    indexed = next((row for row in load_index().assets if row.category == kind and row.filename == filename), None)
    directory = (LIBRARY_ROOT / kind).resolve()
    path = (directory / filename).resolve()
    if not indexed or not path.is_relative_to(directory) or not path.is_file():
        raise HTTPException(404, "فایل در فهرست کتابخانه پیدا نشد.")
    return str(path)


_STILL_ASSET = re.compile(r"(?P<name>.+)\.panel-still-[0-9]+\.mp4")


def _stage_layer_attachment(job, source: dict, still_duration: float | None = None):
    from pathlib import Path
    import os
    import shutil
    from tempfile import NamedTemporaryFile

    original = Path(source["path"])
    name = Path(source["filename"]).name
    if still_duration is not None:
        from math import ceil
        frames = ceil(still_duration * 15)
        name = f"{name[:210]}.panel-still-{frames}.mp4"
    relative = Path("assets", "panel-stills" if still_duration is not None else "panel-media", source["id"], name)
    dest = job.dir / relative
    if not original.is_file():
        raise HTTPException(404, "فایل بارگذاری‌شده دیگر در دسترس نیست.")
    if dest.is_file():
        return relative.as_posix(), None
    dest.parent.mkdir(parents=True, exist_ok=True)
    if still_duration is not None:
        _prepare_still(original, dest, frames)
        return relative.as_posix(), dest
    try:
        os.link(original, dest)
    except OSError:
        try:
            with NamedTemporaryFile(dir=dest.parent, delete=False) as stream:
                temporary = Path(stream.name)
                try:
                    with original.open("rb") as read:
                        shutil.copyfileobj(read, stream, 1024 * 1024)
                    stream.flush()
                    os.replace(temporary, dest)
                finally:
                    temporary.unlink(missing_ok=True)
        except OSError as exc:
            raise HTTPException(422, "رسانه برای آماده‌سازی رندر قابل خواندن نیست.") from exc
    return relative.as_posix(), dest


def _prepare_still(original, destination, frames: int):
    """Adapt an owned still to the existing EditPlan video B-roll contract."""
    import os
    import subprocess
    from pathlib import Path
    from tempfile import NamedTemporaryFile

    from PIL import Image, ImageOps, UnidentifiedImageError

    with NamedTemporaryFile(dir=destination.parent, suffix=".png", delete=False) as still:
        still_path = Path(still.name)
    video_path = still_path.with_suffix(".mp4")
    try:
        with Image.open(original) as image:
            if image.width * image.height > 24_000_000:
                raise ValueError("Image exceeds renderer pixel budget")
            if image.format not in {"JPEG", "PNG", "WEBP"} or getattr(image, "is_animated", False):
                raise ValueError("A static JPEG, PNG or WebP is required")
            content = ImageOps.exif_transpose(image)
            content.thumbnail((1920, 1920))
            content.convert("RGB").save(still_path)
        subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                        "-loop", "1", "-framerate", "15", "-i", str(still_path), "-frames:v", str(frames),
                        "-an", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-threads", "2",
                        "-preset", "veryfast", "-pix_fmt", "yuv420p", str(video_path)],
                       check=True, capture_output=True, timeout=75)
        os.replace(video_path, destination)
    except (ValueError, OSError, Image.DecompressionBombError, UnidentifiedImageError, subprocess.SubprocessError) as exc:
        raise HTTPException(422, "عکس قابل پردازش نیست. یک JPEG، PNG یا WebP ثابت بارگذاری کنید.") from exc
    finally:
        still_path.unlink(missing_ok=True)
        video_path.unlink(missing_ok=True)


def _apply_layer(plan: dict, change: LayerChange, asset_path: str | None = None) -> dict:
    from copy import deepcopy
    from engine.operations import segment_spans

    key = _LAYER_KEYS[change.kind]
    result = deepcopy(plan)
    if change.kind == "music":
        result[key] = None if change.operation == "remove" else {
            **(result.get(key) or {}), "file": asset_path or _library_file(change.kind, change.filename), "volume_db": change.volume_db,
        }
        return result
    rows = result.setdefault(key, [])
    if change.operation in {"remove", "replace"} and (change.index is None or change.index >= len(rows)):
        raise HTTPException(404, "لایه پیدا نشد.")
    if change.operation == "remove":
        rows.pop(change.index)
        return result

    duration = segment_spans(plan)[-1].end
    if change.start >= duration:
        raise HTTPException(422, "زمان آغاز باید داخل خروجی باشد.")
    if change.kind in {"caption", "broll"} and not change.start < change.end <= duration:
        raise HTTPException(422, "یک بازهٔ کامل داخل خروجی انتخاب کنید.")
    if change.kind == "caption":
        if not change.text.strip():
            raise HTTPException(422, "متن را وارد کنید.")
        item = {"start": change.start, "end": change.end, "text": change.text.strip(), "position": change.position}
        if change.caption_style is not None:
            item["style"] = change.caption_style
        if change.highlight is not None:
            word = change.highlight.strip()
            if word and word not in item["text"]:
                raise HTTPException(422, "عبارت برجسته باید داخل متن زیرنویس باشد.")
            item["highlighted_word"] = word or None
    else:
        item = {"at": change.start, "file": asset_path or _library_file(change.kind, change.filename)}
        if change.kind == "sfx":
            item["volume_db"] = change.volume_db
        else:
            item.update(duration=change.end - change.start, **{"in": change.source_in, "query": None})
    if change.operation == "replace":
        updated = {**rows[change.index], **item}
        if change.kind == "caption" and (updated.get("highlighted_word") or "") not in updated["text"]:
            updated.pop("highlighted_word", None)
        rows[change.index] = updated
    elif len(rows) < 200:
        rows.append(item)
    else:
        raise HTTPException(422, "حداکثر تعداد لایه‌های این نوع ثبت شده است.")
    if change.kind == "broll":
        # MLT's single cutaway playlist places entries sequentially. Preserve
        # the user's output coordinates instead of letting an overlap shift them.
        fps = result["canvas"]["fps"]
        rows.sort(key=lambda row: row["at"])
        last_frame = 0
        for row in rows:
            start = round(row["at"] * fps)
            length = round(row["duration"] * fps)
            if length < 1:
                raise HTTPException(422, "لایهٔ بی‌رول باید دست‌کم یک فریم باشد.")
            if start < last_frame:
                raise HTTPException(422, "بازه‌های بی‌رول روی این ردیف نباید هم‌پوشانی داشته باشند.")
            last_frame = start + length
    return result


@router.patch("/projects/{project_id}/layers")
async def change_layer(request: Request, project_id: str, body: LayerChange):
    from app import jobs, plan_versions

    user = studio._user(request)
    await _native_job(request, project_id)
    with _lock(user, project_id):
        job, plan = await _native_job(request, project_id)
        latest = await asyncio.to_thread(plan_versions.latest_version, job)
        if (latest["version"] if latest else None) != body.version or job.render.status in {"queued", "running"}:
            raise HTTPException(409, "برنامه تغییر کرده یا در حال رندر است.")
        asset_path = None
        staged = None
        if body.attachment_id and body.operation != "remove":
            if body.filename or body.kind == "caption":
                raise HTTPException(422, "برای لایه فقط یک منبع متناسب انتخاب کنید.")
            project = await repo.get_project(project_id, user)
            try:
                source, = await repo.get_attachments([body.attachment_id], project["conversation_id"], user)
            except KeyError as exc:
                raise HTTPException(404, "فایل در همین پروژه پیدا نشد.") from exc
            if source["kind"] not in ({"image", "video"} if body.kind == "broll" else {"audio"}):
                raise HTTPException(422, "نوع فایل با لایه سازگار نیست.")
            still_duration = None
            if source["kind"] == "image":
                still_duration = body.end - body.start
                if not 0 < still_duration <= 60 or body.source_in != 0:
                    raise HTTPException(422, "برای عکس یک بازهٔ حداکثر ۶۰ ثانیه‌ای انتخاب کنید.")
            asset_path, staged = await asyncio.to_thread(_stage_layer_attachment, job, source, still_duration)
        try:
            candidate = await asyncio.to_thread(_apply_layer, plan, body, asset_path)
            if candidate != plan:
                _, errors = await asyncio.to_thread(jobs.save_plan, job, candidate, source="user_ui",
                                                   operations=[{"op": body.operation, "kind": body.kind}])
                if errors:
                    if body.kind == "broll":
                        raise HTTPException(422, "بازهٔ بی‌رول باید داخل طول فایل ویدیویی انتخاب‌شده باشد.")
                    raise HTTPException(422, "این لایه با رسانه یا قالب رندر فعلی سازگار نیست.")
        except HTTPException:
            if staged:
                staged.unlink(missing_ok=True)
            raise
    return await native_segments(request, project_id)


class CaptionFontChange(BaseModel):
    model_config = {"extra": "forbid"}
    version: int | None = None
    family: str | None = Field(default=None, min_length=1, max_length=160)
    font_id: str | None = Field(default=None, min_length=1, max_length=160)


@router.get("/caption-fonts")
def caption_fonts(request: Request, persian: bool = False):
    from engine.font_library import planner_font_options

    studio._user(request)
    return planner_font_options(persian=persian)


@router.get("/caption-fonts/file")
def bundled_caption_font(request: Request, family: str):
    from fastapi.responses import FileResponse
    from engine.font_library import render_font_path
    from engine.schema import Canvas

    studio._user(request)
    if not 1 <= len(family) <= 160:
        raise HTTPException(404, "فونت پیدا نشد.")
    path = render_font_path(Canvas(width=2, height=2, fps=30, caption_font=family))
    if not path:
        raise HTTPException(404, "فونت پیدا نشد.")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})


@router.patch("/projects/{project_id}/caption-font")
async def set_caption_font(request: Request, project_id: str, body: CaptionFontChange):
    from app import jobs, plan_versions
    from engine.font_library import render_font_path, resolve_font
    from engine.schema import Canvas

    user = studio._user(request)
    await _native_job(request, project_id)
    with _lock(user, project_id):
        job, plan = await _native_job(request, project_id)
        latest = await asyncio.to_thread(plan_versions.latest_version, job)
        if (latest["version"] if latest else None) != body.version or job.render.status in {"queued", "running"}:
            raise HTTPException(409, "برنامه تغییر کرده یا در حال رندر است.")
        canvas = {**plan["canvas"], "caption_font": body.family, "caption_font_id": body.font_id}
        try:
            if body.font_id:
                entry = await asyncio.to_thread(resolve_font, body.font_id)
                if entry.get("archived_at"):
                    raise ValueError("Archived font")
                canvas["caption_font"] = entry["family"]
            elif body.family and not await asyncio.to_thread(render_font_path, Canvas.model_validate(canvas)):
                raise ValueError("Missing renderer font")
        except ValueError as exc:
            raise HTTPException(422, "فونت انتخاب‌شده برای رندر در دسترس نیست.") from exc
        candidate = {**plan, "canvas": canvas}
        if candidate != plan:
            _, errors = await asyncio.to_thread(jobs.save_plan, job, candidate, source="user_ui",
                                               operations=[{"op": "caption_font", "family": canvas["caption_font"], "font_id": body.font_id}])
            if errors:
                raise HTTPException(422, "فونت با برنامهٔ رندر سازگار نیست.")
    return await native_segments(request, project_id)
