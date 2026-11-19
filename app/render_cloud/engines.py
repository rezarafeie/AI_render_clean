"""One render boundary, reusing current engine entrypoints unchanged."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .contracts import RenderSpec


def prepared_json(path):
    # Prepared scripts/configs are small metadata, never unbounded video payloads.
    if path.stat().st_size > 16 * 1024**2:
        raise ValueError('Prepared metadata exceeds allowance')
    return json.loads(path.read_text())


def verify_inputs(spec: RenderSpec, workspace: Path):
    root = workspace.resolve()
    for asset in spec.assets:
        path = root / asset.path
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError('Asset path is not a regular owned workspace file')
        if path.stat().st_size != asset.size:
            raise ValueError('Asset size mismatch')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != asset.sha256:
            raise ValueError('Asset hash mismatch')


def execute(spec: RenderSpec, workspace: Path, *, on_progress=None, should_cancel=None) -> Path:
    old = {key: os.environ.get(key) for key in spec.runtime_env}
    os.environ.update(spec.runtime_env)
    try:
        return _execute(spec, workspace, on_progress=on_progress, should_cancel=should_cancel)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _execute(spec: RenderSpec, workspace: Path, *, on_progress=None, should_cancel=None) -> Path:
    """Called only in a restricted worker with already authorized, prepared inputs.

    External URLs/absolute paths in project contents require a portability audit
    before cloud admission. This function is not a public submission endpoint.
    """
    verify_inputs(spec, workspace)
    output = workspace / spec.output
    if output.exists() or output.is_symlink():
        raise ValueError('Output already exists')
    if should_cancel and should_cancel():
        raise InterruptedError('Render cancelled')
    entry = workspace / spec.entrypoint
    if spec.engine == 'hyperframes_page':
        from engine.hyperframes.standalone import render
        render(entry.parent, output, timeout=spec.timeout_seconds,
               on_progress=on_progress, should_cancel=should_cancel,
               frames=round(spec.duration_seconds * spec.fps))
    elif spec.engine == 'hyperframes_project':
        from engine.hyperframes.renderer import render_project
        render_project(entry.parent, output, timeout=spec.timeout_seconds,
                       on_progress=on_progress, should_cancel=should_cancel)
    elif spec.engine == 'hyperframes_product':
        from engine.hyperframes.product_reel import _run_cli
        _run_cli(entry.parent, output, timeout=spec.timeout_seconds,
                 on_progress=on_progress, should_cancel=should_cancel,fmt=spec.export_format)
    elif spec.engine == 'talking_5':
        from pydantic import TypeAdapter
        from creative.style_packs import StylePack
        from engine.talking_styles import talking_2, talking_5
        from .contracts import relative_path
        data = prepared_json(entry)

        def owned(value):
            path = workspace / relative_path(value)
            if not path.resolve().is_relative_to(workspace.resolve()) or not path.is_file():
                raise ValueError('Talking 5 asset outside workspace')
            return path
        plan = TypeAdapter(talking_2.ReelPlan).validate_python(data['plan'])
        plan.script, plan.pack = data['script'], StylePack.model_validate(data['pack'])
        plan.sentences, plan.creative_plan, plan.effects = data['sentences'], data['creative_plan'], data['fx']
        previous = os.environ.get('HYPERFRAMES_GSAP')
        os.environ['HYPERFRAMES_GSAP'] = str(owned(data['gsap']))      # the layers' pages need GSAP and the worker has no network
        try:
            talking_5.compose(owned(data['video']), plan, output, work_dir=workspace / 'render-work',
                              music=owned(data['music']) if data.get('music') else None, pack=plan.pack, fx=data['fx'],
                              hook=owned(data['hook']) if data.get('hook') else None, on_progress=on_progress)
        finally:
            if previous is None:
                os.environ.pop('HYPERFRAMES_GSAP', None)
            else:
                os.environ['HYPERFRAMES_GSAP'] = previous
    elif spec.engine.startswith('talking_'):
        from pydantic import TypeAdapter
        from engine.talking_styles import talking_1,talking_2
        from engine.talking_reel import get_style
        data = prepared_json(entry)
        if data.get('style')!=spec.engine:
            raise ValueError('Talking style differs from approved manifest')
        module=get_style(spec.engine)
        plan = TypeAdapter(talking_1.ReelPlan if spec.engine=='talking_1' else talking_2.ReelPlan).validate_python(data['plan'])
        for shot in plan.shots:
            if getattr(shot,'picture',None):
                from .contracts import relative_path
                path=workspace/relative_path(shot.picture)
                if not path.resolve().is_relative_to(workspace.resolve()) or not path.is_file():
                    raise ValueError('Talking picture outside workspace')
                shot.picture=str(path)
        if spec.engine=='talking_3':
            plan.titles=data.get('titles',[])
            for key in ('full_pictures','card_pictures'):
                indices=data.get(key,[])
                if any(type(i) is not int or not 0<=i<len(plan.shots) for i in indices):
                    raise ValueError('Invalid cinematic shot references')
                setattr(plan,key,{id(plan.shots[i]) for i in indices})
        options = data['options']
        for key in ('music','logo_path'):
            if options.get(key):
                from .contracts import relative_path
                path = workspace/relative_path(options[key])
                if not path.resolve().is_relative_to(workspace.resolve()) or not path.is_file():
                    raise ValueError('Talking asset outside workspace')
                options[key] = path
        from .contracts import relative_path
        video = workspace/relative_path(data['video'])
        module.render(video,plan,output,work_dir=workspace/'render-work',on_progress=on_progress,**options)
    elif spec.engine == 'localize':
        from engine import localize
        from .contracts import relative_path
        data = prepared_json(entry)

        def owned(value):
            path = workspace / relative_path(value)
            if not path.resolve().is_relative_to(workspace.resolve()) or not path.is_file():
                raise ValueError('Localize asset outside workspace')
            return path
        placements = [{**p, 'file': str(owned(p['file']))} for p in data['placements']]
        localize.render(owned(data['video']), data['state'], placements, output, work_dir=workspace / 'render-work',
                        fonts_dir=Path(localize.__file__).resolve().parents[1] / 'presets/fonts',
                        music=owned(data['music']) if data.get('music') else None,
                        logo=owned(data['logo']) if data.get('logo') else None,
                        on_progress=on_progress, only_covers=bool(data.get('only_covers')))
    elif spec.engine == 'mlt':
        from engine.render import render
        render(entry, output, on_progress=on_progress, **spec.mlt_options.model_dump())
    elif spec.engine == 'claude_motion':
        from engine.claude_motion_renderer import render
        render(workspace, output, timeout=spec.timeout_seconds, on_progress=on_progress)
    elif spec.engine == 'ffmpeg_job':
        _ffmpeg_job(prepared_json(entry), workspace, output, spec.timeout_seconds, on_progress, should_cancel)
    else:
        from engine.remotion_renderer import render
        # Remotion has a hard subprocess deadline; supervisor handles cancellation
        # of its entire process group (including Chromium and FFmpeg).
        render(prepared_json(entry), output, job_dir=workspace,
               timeout=spec.timeout_seconds, on_progress=on_progress)
    if should_cancel and should_cancel():
        raise InterruptedError('Render cancelled')
    if not output.is_file() or not output.stat().st_size:
        raise RuntimeError('Renderer produced no output')
    return output


def _ffmpeg_job(job, workspace: Path, output: Path, timeout, on_progress=None, should_cancel=None):
    """Heavy ffmpeg passes of any engine (cuts, grades, long encodes; Lite, Medium and the Pro agent) on a worker. Only the ffmpeg binary runs, step after step, in the
    workspace; every argument that names a file must stay inside it (no absolute paths, no ..), no protocol other than plain files, and the last
    step writes `result.<ext>`, which becomes the output."""
    import re
    import shutil
    import subprocess
    import time
    steps = job.get('steps') if isinstance(job, dict) else None
    if not isinstance(steps, list) or not 1 <= len(steps) <= 12:
        raise ValueError('ffmpeg_job needs 1-12 steps')
    root = workspace.resolve()
    bad = re.compile(r'^(?:/|~)|(?:^|/)\.\.(?:/|$)|^[a-z][a-z0-9+.-]*:(?!\d)', re.I)
    started, budget = time.monotonic(), max(60, int(timeout))
    for index, args in enumerate(steps):
        if not isinstance(args, list) or not args or not all(isinstance(a, str) for a in args):
            raise ValueError('every ffmpeg_job step is a list of strings')
        for arg in args:
            if bad.search(arg) and not re.fullmatch(r'[0-9:.\-]+', arg):
                raise ValueError(f'ffmpeg_job argument not allowed: {arg[:80]}')
        if should_cancel and should_cancel():
            raise InterruptedError('Render cancelled')
        left = budget - (time.monotonic() - started)
        if left <= 5:
            raise TimeoutError('ffmpeg_job time is over')
        done = subprocess.run(['ffmpeg', '-hide_banner', '-nostdin', '-y', *args], cwd=root, capture_output=True, text=True, timeout=left)
        if done.returncode != 0:
            raise RuntimeError(f'ffmpeg step {index + 1} failed: ' + (done.stderr or '')[-600:])
        if on_progress:
            on_progress(int(100 * (index + 1) / len(steps)))
    result = next((p for p in root.glob('result.*') if p.is_file()), None)
    if result is None:
        raise RuntimeError('the last ffmpeg_job step must write result.<ext>')
    shutil.move(str(result), str(output))
