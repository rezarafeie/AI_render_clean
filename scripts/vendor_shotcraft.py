"""Vendor a reviewed, data-only Shotcraft reference subset; never run upstream code.

Usage: python scripts/vendor_shotcraft.py /path/to/installed/video-shotcraft
The installer must have pinned upstream to REVISION before this import.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sys

REVISION = "5a2e98daade313c4f376120f38427eb19a108e8c"
NAMES = ("bezier-source-converge-merge", "text-column-converge", "card-stack",
         "title-demote-to-label", "card-flip-reveal", "before-after-slider-scrub",
         "chart-live-moves", "circle-match-iris")


def main():
    source = Path(sys.argv[1]).resolve()
    target = Path(__file__).resolve().parents[1] / "creative/shotcraft_data"
    library = json.loads((source / "gallery/api/library.json").read_text())
    cards = {card["name"]: card for card in library["cards"]}
    files, selected = {"LICENSE"}, []
    for name in NAMES:
        card = cards[name]
        recipe = Path(card["source"])
        demo = source / "demos" / recipe.parent.name / name
        demos = sorted(path.relative_to(source).as_posix() for path in demo.glob("*.tsx"))
        if not demos:
            raise SystemExit(f"Missing reference implementation: {name}")
        files.update([recipe.as_posix(), *demos])
        selected.append({"name": name, "recipe": recipe.as_posix(), "demos": demos,
                         "styles": [s["key"] for s in card["styles"]]})
    hashes = {}
    for name in sorted(files):
        src = (source / name).resolve()
        if not src.is_relative_to(source) or src.is_symlink():
            raise SystemExit("Invalid source reference")
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        hashes[name] = hashlib.sha256(dest.read_bytes()).hexdigest()
    (target / "manifest.json").write_text(json.dumps({
        "repository": "https://github.com/Vincentwei1021/video-shotcraft", "revision": REVISION,
        "license": "Apache-2.0", "usage": "reference-only; TSX is not executed by HyperFrames",
        "cards": selected, "sha256": hashes}, ensure_ascii=False, indent=2))
    print(f"Vendored {len(selected)} reference cards, {len(files)} files; no code executed.")


if __name__ == "__main__":
    main()
