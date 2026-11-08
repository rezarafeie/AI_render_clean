"""Private CI verification of the existing Remotion composition in the native worker."""
import json
from pathlib import Path
import tempfile
import time

from PIL import Image
from app.render_cloud.parity import probe
from app.render_cloud.prepare import freeze
from app.render_cloud.supervisor import run

with tempfile.TemporaryDirectory(prefix='remotion-probe-') as directory:
    root = Path(directory)
    Image.new('RGB', (320, 180), '#517cac').save(root / 'visual.png')
    (root / 'render.json').write_text(json.dumps({
        'scenes': [{'frames': 15, 'title': 'آزمون رندر', 'asset': 'visual.png'}],
    }))
    spec = freeze(root, ['render.json', 'visual.png'], job_id='remotion-probe',
                  project_id='synthetic', user_id='synthetic', engine='remotion',
                  entrypoint='render.json', duration_seconds=.5, width=1080, height=1920,
                  fps=30, timeout_seconds=165, workspace_bytes=256 * 1024**2,
                  runtime_env={'REMOTION_CONCURRENCY': '1'})
    started = time.monotonic()
    out = run(spec, root, isolate_network=True,
              on_progress=lambda value: print('Remotion progress', value, flush=True))
    media = probe(out)
    assert (media['width'], media['height'], media['fps'], media['frames']) == (1080, 1920, '30', 15)
    print(json.dumps({'elapsed_seconds': time.monotonic()-started, **media}), flush=True)
