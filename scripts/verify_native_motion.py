"""Reproducible, no-AI native-code QA fixture for the existing HF checker.

Build only; never starts a service, sends a provider request or renders on its
own. Use the existing HyperFrames check/snapshot commands on the output.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from creative.motion_graphic import MotionPlan, ScenePlan, assemble_scenes, author_scene, write_project
from creative.native_motion import NativeMotion


def build(directory: Path, aspect: str, gsap: Path | None = None):
    if directory.exists():
        raise ValueError("Use a new QA directory; existing projects are never overwritten")
    if gsap:
        if not gsap.is_file() or "GSAP 3.14.2" not in gsap.read_text()[:400]:
            raise ValueError("Expected existing pinned GSAP 3.14.2")
        import engine.hyperframes.assets as assets
        assets.ensure_gsap = lambda: gsap
    specs = [
        NativeMotion(resource_id="hyperframes:headline-slam", text="یک شروع متفاوت", accent="blue"),
        NativeMotion(resource_id="hyperframes:count-up", text="تعداد نمونه", end_value=320, suffix=" نفر"),
        NativeMotion(resource_id="hyperframes:headline-slam", text="Keep moving forward", accent="violet"),
        NativeMotion(resource_id="hyperframes:cta-close", text="حالا شروع کنیم", button_label="قدم بعدی"),
    ]
    plan = MotionPlan(title="Native code QA", format=aspect, duration=16,
                      scenes=[ScenePlan(headline=s.text, idea="QA only, not a content proposal", start=i*4,
                                        end=(i+1)*4, native_component=s) for i, s in enumerate(specs)])
    directory.mkdir(parents=True)
    page = assemble_scenes(plan, [author_scene(plan, i+1, "QA") for i in range(len(specs))])
    write_project(directory, page)
    return directory


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--format", choices=("vertical", "horizontal", "square"), default="vertical")
    parser.add_argument("--gsap", type=Path, help="Reuse an already downloaded pinned runtime")
    args = parser.parse_args()
    print(build(args.directory, args.format, args.gsap))
