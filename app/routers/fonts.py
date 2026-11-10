"""Fonts API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from engine.schema import PROJECT_ROOT

router = APIRouter(prefix="/fonts", tags=["fonts"])
legacy_router = APIRouter(tags=["fonts"])


@router.get("")
def list_fonts():
    from engine.captions import fonts_dir, load_style
    directory = fonts_dir(load_style("rafiei_reel")) or PROJECT_ROOT / "presets" / "fonts"
    names = ({p.stem for p in directory.rglob("*")
              if p.is_file() and p.suffix.lower() in {".ttf", ".otf"}}
             if directory.is_dir() else set())
    from engine.font_library import list_library
    names.update(e["family"] for e in list_library()["approved"] if e.get("kind") == "font_file")
    from creative import font_catalog
    names.update(c for f in font_catalog.load() for c in f["css_families"])
    return {"fonts": sorted(names)}


def _pro_files() -> dict[str, "Path"]:
    """(font id, file name) -> file, for every face in the catalog and the studio's own caption fonts."""
    from pathlib import Path
    from creative import font_catalog
    files: dict[str, Path] = {}
    kit = PROJECT_ROOT / "presets" / "fonts"
    builtin = {"ray": ["RAY-LIGHT.TTF", "RAY.TTF", "RAY-MEDIUM.TTF", "RAY-BOLD.TTF", "RAY-EXTRABOLD.TTF", "RAY-BLACK.TTF"], "vazir": ["Vazirmatn-Regular.ttf"], "kharazmi": ["IRAN_Kharazmi/IRAN Kharazmi.ttf"]}
    for font in font_catalog.load():
        if font.get("builtin"):
            for rel in builtin.get(font["id"], []):
                files[f"{font['id']}/{Path(rel).name}"] = kit / rel
        for face in font["faces"]:
            files[f"{font['id']}/{Path(face['file']).name}"] = font_catalog.DIR / face["file"]
    return files


@router.get("/pro")
def pro_fonts():
    """The font library: every family with what it is for, its faces (for live previews in the browser) and the specimen image."""
    from pathlib import Path
    from creative import font_catalog
    files = _pro_files()
    out = []
    for font in font_catalog.load():
        faces = [{"css_family": f["css_family"], "weight": f["weight"], "variable": f["variable"], "axes": f["axes"], "url": f"/api/fonts/pro/file/{font['id']}/{Path(f['file']).name}"}
                 for f in font["faces"]]
        if font.get("builtin"):
            weights = {"RAY-LIGHT.TTF": "300", "RAY.TTF": "400", "RAY-MEDIUM.TTF": "500", "RAY-BOLD.TTF": "700", "RAY-EXTRABOLD.TTF": "800", "RAY-BLACK.TTF": "900"}
            for key, path in files.items():
                if key.startswith(font["id"] + "/"):
                    faces.append({"css_family": font["family"], "weight": weights.get(path.name, "400"), "variable": False, "axes": {}, "url": f"/api/fonts/pro/file/{key}"})
        out.append({k: font.get(k) for k in ("id", "label", "family", "css_families", "vendor", "designer", "category", "mood", "best_for", "avoid_for", "pairs_with", "note", "weights", "axes", "latin",
                                            "persian_digits", "builtin", "license")} | {"faces": faces, "specimen_url": f"/api/fonts/pro/specimen/{font['id']}"})
    return {"fonts": out}


@router.get("/pro/file/{font_id}/{name}")
def pro_font_file(font_id: str, name: str):
    path = _pro_files().get(f"{font_id}/{name}")
    if not path or not path.is_file():
        raise HTTPException(404, "font file not found")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})


@router.get("/pro/specimen/{font_id}")
def pro_font_specimen(font_id: str):
    from creative import font_catalog
    font = font_catalog.get(font_id)
    path = font_catalog.DIR / font["specimen"] if font else None
    if not path or not path.is_file():
        raise HTTPException(404, "specimen not found")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@legacy_router.get("/font-library")
def get_font_library():
    from engine.font_library import list_library
    return list_library()


class FontTextReference(BaseModel):
    name: str
    copied_text: str
    font_name: str = ""
    visual_reference: str = ""


@legacy_router.post("/font-library/text")
def save_font_text_reference(body: FontTextReference):
    from engine.font_library import add_text_reference
    try:
        return add_text_reference(body.name, body.copied_text, body.font_name, body.visual_reference)
    except ValueError as e:
        raise HTTPException(422, str(e))


@legacy_router.post("/font-library/image")
async def import_font_image(image: UploadFile = File(...)):
    from engine.font_library import add_image_reference
    try:
        return add_image_reference(image.filename or "reference.png", await image.read())
    except ValueError as e:
        raise HTTPException(422, str(e))


@legacy_router.post("/font-library/font")
async def import_font_file(font: UploadFile = File(...)):
    from engine.font_library import add_font_file
    try:
        return add_font_file(font.filename or "font.ttf", await font.read())
    except ValueError as e:
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@legacy_router.post("/font-library/{candidate_id}/approve")
def approve_font(candidate_id: str):
    from engine.font_library import approve
    try:
        return approve(candidate_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@legacy_router.delete("/font-library/{entry_id}")
def delete_font_library_item(entry_id: str):
    from engine.font_library import remove
    try:
        return remove(entry_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@legacy_router.get("/font-library/fonts/{font_id}/file")
def get_approved_font_file(font_id: str):
    from engine.font_library import resolve_font
    try:
        font = resolve_font(font_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return FileResponse(font["path"], filename=font["filename"])


@legacy_router.get("/font-library/candidates/{candidate_id}/file")
def get_candidate_font_file(candidate_id: str):
    from engine.font_library import CANDIDATES, list_library
    candidate = next((e for e in list_library()["candidates"]
                      if e["id"] == candidate_id and e.get("kind") == "font_file"), None)
    if not candidate:
        raise HTTPException(404, "font candidate not found")
    path = CANDIDATES / candidate["filename"]
    if not path.is_file():
        raise HTTPException(404, "font candidate file is missing")
    return FileResponse(path, filename=path.name)
