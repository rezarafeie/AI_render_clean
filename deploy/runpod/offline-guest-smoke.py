"""Synthetic check of the existing HyperFrames renderer inside the offline guest."""
import json
from pathlib import Path
import shutil
import sys
import tempfile

from app.render_cloud.parity import probe
from app.render_cloud.prepare import freeze
from app.render_cloud.supervisor import run


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><script src="./gsap.min.js"></script>
<style>body{margin:0} #root{width:100%;height:100%;position:relative;background:#17384d}
.clip{position:absolute;inset:0;display:grid;place-items:center;color:#fff}
strong{font:28px sans-serif}</style></head>
<body><div id="root" data-composition-id="probe" data-width="320" data-height="180"
data-start="0" data-duration="1"><section class="clip" data-start="0" data-duration="1"
data-track-index="0"><strong id="title">RunPod</strong></section></div>
<script>window.__timelines ||= {}; const tl = gsap.timeline({paused:true});
tl.from("#title",{y:12,opacity:0,duration:.3}); window.__timelines.probe = tl;</script>
</body></html>
"""


def main(gsap):
    with tempfile.TemporaryDirectory(prefix='guest-smoke-') as directory:
        workspace = Path(directory)
        (workspace / 'index.html').write_text(PAGE)
        shutil.copyfile(gsap, workspace / 'gsap.min.js')
        spec = freeze(workspace, ['index.html', 'gsap.min.js'], job_id='guest-smoke',
                      project_id='synthetic', user_id='synthetic', engine='hyperframes_page',
                      entrypoint='index.html', duration_seconds=1, width=320, height=180, fps=30,
                      timeout_seconds=240, workspace_bytes=64 * 1024**2,
                      runtime_env={'HYPERFRAMES_WORKERS': '1'})
        out = run(spec, workspace, isolate_network=True)
        measured = probe(out)
        assert (measured['width'], measured['height'], measured['fps'], measured['frames']) == (320, 180, '30', 30)
        print(json.dumps(measured))


if __name__ == '__main__':
    main(sys.argv[1])
