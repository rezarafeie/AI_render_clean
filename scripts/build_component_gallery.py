"""Execute each pinned HyperFrames source and retain real, public QA previews.

No AI calls. No user assets. Gallery snapshots are demonstrative, not performance
claims or certification of all inputs/formats. Never enables an adapter by itself.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from creative.native_motion import NativeMotion, materialize, source_names, parameter_schema
from creative.motion_graphic import MotionPage, write_project


def run(args):
    import engine.hyperframes.assets as assets
    if not args.gsap.is_file() or "GSAP 3.14.2" not in args.gsap.read_text()[:400]:
        raise ValueError("Supply an existing pinned GSAP 3.14.2 runtime")
    assets.ensure_gsap = lambda: args.gsap
    output = ROOT / "web/public/creative-previews"
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "index.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"schema_version": 1, "items": {}}
    names = args.only or source_names()
    for name in names:
        if name not in source_names():
            raise ValueError("Unknown gallery resource")
        directory = args.work / name
        if directory.exists():
            raise ValueError("Use a fresh work directory; QA sources are not overwritten")
        directory.mkdir(parents=True)
        spec = NativeMotion(resource_id="hyperframes:" + name, text="یک شروع متفاوت", button_label="شروع", suffix=" نفر", end_value=320)
        page = MotionPage(title="Component demonstration", duration=4,
                         scenes_html='<section class="hm-scene" id="s1"><div id="s1-native-host" class="clip" data-composition-id="s1-native" data-composition-src="compositions/s1-native.html" data-start="0" data-duration="4" data-track-index="2" style="position:absolute;inset:0"></div></section>',
                         build_js='tl.to({}, {duration:4}, 0);')
        write_project(directory, page)
        receipt = materialize(directory, spec, "s1-native", 4)
        row = {"id": spec.resource_id, "name": name, "status": "failed", "format": "vertical",
               "demonstration_only": True, "source_sha256": receipt["source_sha256"],
               "parameters": list(parameter_schema(name).values()), "poster": None}
        try:
            result = subprocess.run(["node", str(args.cli), "check", str(directory), "--at", "0.5,1,2,3", "--snapshots", "--json"],
                                    capture_output=True, text=True, timeout=150)
            (directory / "check.log").write_text(result.stdout + "\n" + result.stderr)
            report = json.loads(result.stdout[result.stdout.index("{"):])
            row["browser_ran"] = not report.get("browserSkipped", True)
            row["findings"] = [{"section": section, "code": finding.get("code"), "severity": finding.get("severity")}
                               for section in ("lint", "runtime", "layout", "contrast")
                               for finding in report.get(section, {}).get("findings", [])]
            if result.returncode == 0 and report.get("ok") and row["browser_ran"]:
                row["status"] = "browser-checked"
            pictures = report.get("snapshots", {}).get("files", [])
            if pictures:
                selected = next((p for p in pictures if "2.0s" in p), pictures[len(pictures)//2])
                frame = directory / selected
                if frame.resolve().is_relative_to(directory.resolve()) and frame.is_file():
                    shutil.copy2(frame, output / f"{name}.png")
                    row["poster"] = f"/creative-previews/{name}.png"
                    row["poster_sha256"] = hashlib.sha256(frame.read_bytes()).hexdigest()
        except (subprocess.TimeoutExpired, ValueError, OSError) as error:
            row["error"] = type(error).__name__  # no private paths/stack traces in public manifest
        manifest["items"][row["id"]] = row
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        print(json.dumps({"id": row["id"], "status": row["status"], "poster": row["poster"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--gsap", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--only", nargs="+")
    run(parser.parse_args())
