"""Run every existing Claude-effect compositor on an explicitly synthetic fixture.

This tests real compositor code, NOT MediaPipe tracking or encoded video. Never
uses a user's face/video. The gallery describes this distinction explicitly.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import numpy as np
    from PIL import Image, ImageDraw
    from engine.face_effects import _fx, CATALOG, clean_plan
    W, H = 540, 960
    image = Image.new("RGB", (W, H), "#e3e8ed")
    draw = ImageDraw.Draw(image)
    for x in range(0, W, 60):
        draw.line((x, 0, x, H), fill="#ccd5df")
    draw.rectangle((0, 730, W, H), fill="#b7c5d3")
    draw.ellipse((185, 205, 355, 385), fill="#b78160")
    draw.rounded_rectangle((105, 375, 435, 950), radius=100, fill="#324967")
    mask = Image.new("L", (W, H))
    md = ImageDraw.Draw(mask)
    md.ellipse((185, 205, 355, 385), fill=255)
    md.rounded_rectangle((105, 375, 435, 950), radius=100, fill=255)
    pixels = np.asarray(image).copy()
    matte = np.asarray(mask, dtype=np.float32) / 255
    output = ROOT / "web/public/creative-previews"
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "items": {}}
    for item in CATALOG:
        plan = {"fx":item["id"], "start":0, "end":4}
        plan.update({v["key"]:v["default"] for v in item.get("options", [])})
        if item.get("text"):
            plan["text"] = item["text"].get("default", "")
        row = {"id":"claude-effects:"+item["id"], "name":"claude-"+item["id"],
               "status":"failed", "format":"vertical", "demonstration_only":True,
               "tracking_verified":False, "fixture":"synthetic geometry and fixed matte",
               "description":item["description"], "use":item.get("use", ""),
               "parameters":item.get("options", []), "poster":None}
        try:
            plan = clean_plan([plan])[0]
            effect = _fx.Fx(plan, 30)
            effect.cards = [image.copy() for _ in range(10)]
            context = _fx.Ctx()
            context.W, context.H, context.fps = W, H, 30
            context.t = context.lt = 1.8
            context.fx, context.fy, context.fw = 270, 295, 150
            context.img = pixels.astype(np.float32) / 255
            context.m = matte.copy()
            _fx.EFFECTS[item["id"]][0](context, effect)
            if context.img.shape != (H, W, 3) or not np.isfinite(context.img).all():
                raise ValueError("Invalid effect pixels")
            result = Image.fromarray((np.clip(context.img, 0, 1)*255).astype(np.uint8))
            file = output / f'claude-{item["id"]}.png'
            result.save(file)
            row.update(status="synthetic-frame-checked", poster="/creative-previews/"+file.name,
                       poster_sha256=hashlib.sha256(file.read_bytes()).hexdigest())
        except Exception as error:
            row["error"] = type(error).__name__
        manifest["items"][row["id"]] = row
        print(json.dumps({"id":row["id"], "status":row["status"]}), flush=True)
    (output / "claude-effects.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    if any(row["status"] == "failed" for row in manifest["items"].values()):
        raise SystemExit("One or more effect compositor checks failed; inspect retained manifest")


if __name__ == "__main__":
    main()
