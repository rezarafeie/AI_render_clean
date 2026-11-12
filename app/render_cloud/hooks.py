"""Thin prepared-render boundaries. Disabled calls do not load cloud SDKs."""
from __future__ import annotations

import contextvars
import json
import os
import tempfile
from html.parser import HTMLParser
from pathlib import Path

identity = contextvars.ContextVar('cloud_render_identity', default=None)


def job_context(function):
    from functools import wraps
    @wraps(function)
    def wrapped(job, *args, **kwargs):
        if not enabled():
            return function(job, *args, **kwargs)
        from app.jobs import _write_status
        def stage(value):
            job.render.message = 'cloud ' + value
            _write_status(job)
        def detail(text):
            job.render.message = text
            _write_status(job)
        token = identity.set((str(job.user_id) if job.user_id else None, job.id, (job.dir,),
                              lambda: job.render.status in {'cancelled','canceled'}, stage, detail))
        try:
            return function(job, *args, **kwargs)
        finally:
            identity.reset(token)
    return wrapped


def enabled():
    return os.environ.get('EDITOR_RENDER_CHILD') != '1' and os.environ.get('RENDER_CLOUD_ENABLE_CLOUD_RENDER', '').lower() in {'1', 'true', 'yes'}


def eligible():
    if not enabled() or not identity.get():
        return False
    from .settings import CloudSettings
    config=CloudSettings().effective()
    return config.enable_cloud_render and config.admin(identity.get()[0]) and config.override!='local'


def hyperframes(project, output, *, engine, timeout, on_progress=None, should_cancel=None,
                user=None, project_id=None, owned_roots=(), on_stage=None,fmt='mp4', on_detail=None):
    if not enabled():
        return False
    who = identity.get()
    if user is None and who:
        user, project_id, owned_roots = who[:3]
        if len(who) > 3 and should_cancel is None:
            should_cancel = who[3]
        if len(who) > 4 and on_stage is None:
            on_stage = who[4]
        if len(who) > 5 and on_detail is None:
            on_detail = who[5]
    if not user:
        # Legacy/anonymous projects are never admitted to paid cloud resources.
        return False
    from .settings import CloudSettings
    if not CloudSettings().effective().admin(user):
        return False
    class Root(HTMLParser):
        attrs = None
        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if self.attrs is None and 'data-composition-id' in values and 'data-duration' in values:
                self.attrs = values
    parser = Root()
    parser.feed((project / 'index.html').read_text())
    attrs = parser.attrs or {}
    try:
        duration, width, height = float(attrs['data-duration']), int(attrs['data-width']), int(attrs['data-height'])
    except (KeyError, ValueError):
        return False
    from .service import render_prepared
    markup = (project / 'index.html').read_text()
    audio = '<audio ' in markup or 'data-has-audio="true"' in markup
    features = [name for enabled, name in ((fmt == 'webm', 'transparent'), ('<canvas' in markup, 'canvas'),
                                          (audio, 'audio')) if enabled]
    return render_prepared(project, output, user=user, project_id=project_id, engine=engine,
                           duration=duration, width=width, height=height, timeout=timeout,
                           on_progress=on_progress, should_cancel=should_cancel,
                           owned_roots=owned_roots, on_stage=on_stage, on_detail=on_detail,
                           export_format=fmt,
                           features=features, audio_required=audio)


def remotion(config, output, *, job_dir, on_progress=None, timeout=5400):
    if not eligible():
        return False
    import hashlib
    import shutil
    from .service import render_prepared
    who = identity.get()
    user, project_id, owned_roots = who[:3]
    root = job_dir.resolve()
    config = json.loads(json.dumps(config))
    look = os.environ.get('REMOTION_LOOK', 'classic')
    if look == 'cinematic':
        from engine.remotion_renderer import _enrich
        _enrich(config, root)
    # Called after existing renderer argument validation/enrichment. Rebase only
    # file references, not times, layout or creative decisions.
    with tempfile.TemporaryDirectory(prefix='editorgpt-remotion-input-') as directory:
        staged = Path(directory)
        def asset(value):
            path = Path(value)
            source = (path if path.is_absolute() else root/path).resolve(strict=True)
            from engine.remotion_renderer import ROOT
            approved = (root, *(Path(p).resolve() for p in owned_roots), (ROOT/'assets/music').resolve())
            if not any(source.is_relative_to(p) for p in approved) or not source.is_file():
                raise ValueError('Remotion asset is outside approved roots')
            name = 'assets/' + hashlib.sha256(str(source).encode()).hexdigest() + source.suffix
            target = staged / name
            target.parent.mkdir(exist_ok=True)
            if not target.exists():
                shutil.copy2(source, target)
            return name
        for scene in config['scenes']:
            for key in ('asset', 'narration'):
                if scene.get(key):
                    scene[key] = asset(scene[key])
            scene['supporting_assets'] = [asset(p) for p in scene.get('supporting_assets', [])]
        if config.get('music'):
            config['music'] = asset(config['music'])
        (staged/'render.json').write_text(json.dumps(config))
        frames = sum(s['frames'] for s in config['scenes'])
        native = config.get('version') == 3
        width, height = (int(config['width']),int(config['height'])) if native else (1080,1920)
        version = config.get('version') if config.get('version') in (2, 3) else 1
        scenes = config['scenes']
        narration = any(scene.get('narration') for scene in scenes)
        music = bool(config.get('music'))
        images = all(Path(scene.get('asset') or '').suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'}
                     for scene in scenes)
        features = [f'version:{version}', f'scenes:{len(scenes)}', f'look:{look}']
        features.extend(name for enabled, name in ((native, 'native-shotcraft'), (images, 'image-source'),
                        (narration, 'narration'), (music, 'music'),
                        (any(s.get('supporting_assets') for s in scenes), 'supporting-assets')) if enabled)
        return render_prepared(staged, output, user=user, project_id=project_id, engine='remotion',
                               duration=frames/30, width=width, height=height, timeout=timeout or 5400,
                               on_progress=on_progress, entrypoint='render.json',
                               features=features,
                               lock_root=job_dir,
                               should_cancel=who[3] if len(who) > 3 else None,
                               on_stage=who[4] if len(who) > 4 else None, on_detail=who[5] if len(who) > 5 else None,
                               audio_required=music or narration)


def mlt(project_file, output, *, on_progress=None, **options):
    if not eligible():
        return False
    import hashlib
    import shutil
    import xml.etree.ElementTree as ET
    from engine import render as engine_render
    from .service import render_prepared, CloudRenderError
    from .settings import CloudSettings
    who = identity.get()
    root = project_file.parent.resolve()
    data = project_file.read_text()
    if '<!DOCTYPE' in data.upper() or '<!ENTITY' in data.upper():
        raise CloudRenderError('MLT external entities are not allowed')
    tree = ET.fromstring(data)
    profile = tree.find('profile')
    main = tree.find("tractor[@id='main']")
    if profile is None or main is None or not str(main.get('out','')).isdigit():
        return False
    width, height, fps = engine_render._profile_from_mlt(data)
    frames = int(main.get('out')) + 1
    style = options.get('style_override') or engine_render.load_style(options.get('style_name','rafiei_reel'))
    if options.get('preview'):
        scale = min(1.0,max(.1,float(style.get('render',{}).get('preview_scale',.5))))
        width, height = max(2,int(width*scale)&~1), max(2,int(height*scale)&~1)
    caption_properties = {'ai-render:caption_font_file', 'ai-render:burn_ass', 'ai-render:captions_ass'}
    render_settings = style.get('render', {})
    preset = 'veryfast' if options.get('preview') else render_settings.get('preset', 'medium')
    if not isinstance(preset, str) or preset not in {
        'ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow', 'placebo',
    }:
        return False
    features = [f'mlt-preset:{preset}']
    if any(prop.text and prop.get('name') in caption_properties for prop in tree.iter('property')):
        features.append('subtitles')
    if options.get('preview'):
        features.append('preview')
    if options.get('apply_loudnorm'):
        features.append('loudnorm')
    if options.get('style_override') or options.get('crf_override') is not None:
        features.append('custom-export')
    with tempfile.TemporaryDirectory(prefix='editorgpt-mlt-input-') as directory:
        staged = Path(directory)
        approved = [root, *(Path(p).resolve() for p in who[2]),
                    (Path(engine_render.__file__).resolve().parents[1]/'presets/fonts').resolve(),
                    (Path(engine_render.__file__).resolve().parents[1]/'assets/music').resolve()]
        def copy(value):
            path = Path(value)
            source = (path if path.is_absolute() else root/path).resolve()
            if not source.exists():
                if path.is_absolute() or '://' in value:
                    raise ValueError('Non-portable MLT resource')
                return value  # Native colour/text producers are not filesystem assets.
            if not any(source.is_relative_to(p) for p in approved):
                raise ValueError('MLT resource outside owned roots')
            name = 'assets/' + hashlib.sha256(str(source).encode()).hexdigest() + (source.suffix if source.is_file() else '')
            target = staged/name
            target.parent.mkdir(exist_ok=True)
            if not target.exists():
                if source.is_dir():
                    if any(p.is_symlink() for p in source.rglob('*')):
                        raise ValueError('Non-portable font directory')
                    shutil.copytree(source,target)
                else:
                    shutil.copy2(source,target)
            return name
        try:
            for prop in tree.iter('property'):
                if prop.get('name') in {'resource','warp_resource','ai-render:caption_font_file','ai-render:burn_ass','ai-render:burn_ass_fontsdir','ai-render:captions_ass'} and prop.text:
                    prop.text = copy(prop.text)
        except (OSError, ValueError):
            if CloudSettings().enable_local_fallback:
                return False
            raise CloudRenderError('MLT assets are not portable') from None
        tree.set('root','.')
        ET.ElementTree(tree).write(staged/'project.mlt',encoding='unicode')
        return render_prepared(staged, output, user=who[0], project_id=who[1], engine='mlt',
                               duration=frames/fps,width=width,height=height,fps=fps,
                               entrypoint='project.mlt',mlt_options=options,on_progress=on_progress,
                               features=features,
                               should_cancel=who[3] if len(who)>3 else None,
                               on_stage=who[4] if len(who)>4 else None, on_detail=who[5] if len(who)>5 else None, lock_root=root)


def talking(video,plan,output,*,style='talking_1',on_progress=None,**options):
    if not eligible():
        return False
    import dataclasses
    import hashlib
    import shutil
    from engine.talking_styles import talking_1 as engine
    from engine.talking_styles import talking_2
    from .service import render_prepared
    who=identity.get()
    allowed_keys={'hook','highlight','name','title','work_dir','music','cta','render_settings','logo_path','on_stage'}
    if style not in {'talking_1','talking_2','talking_3','talking_4'} or set(options)-allowed_keys or not isinstance(plan,(engine.ReelPlan,talking_2.ReelPlan)):
        return False
    if set(vars(plan))-{f.name for f in dataclasses.fields(plan)}-({'titles','full_pictures','card_pictures'} if style=='talking_3' else set()):
        return False
    with tempfile.TemporaryDirectory(prefix='editorgpt-talking-input-') as directory:
        staged=Path(directory)
        def asset(value,*,brand=False):
            source=Path(value).resolve(strict=True)
            approved=[*(Path(p).resolve() for p in who[2]),(engine.PROJECT_ROOT/'assets/music').resolve()]
            if brand and source==engine.LOGO.resolve():
                approved.append(source.parent)
            if not any(source.is_relative_to(root) for root in approved) or not source.is_file():
                raise ValueError('Talking asset is not owned or library-approved')
            name='assets/'+hashlib.sha256(str(source).encode()).hexdigest()+source.suffix
            target=staged/name
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(source,target)
            return name
        source=asset(video)
        plan_data=dataclasses.asdict(plan)
        for shot in plan_data['shots']:
            if shot.get('picture'): shot['picture']=asset(shot['picture'])
        clean={k:v for k,v in options.items() if k not in {'work_dir','on_stage','music','logo_path'}}
        if options.get('music'): clean['music']=asset(options['music'])
        logo=Path(options.get('logo_path') or engine.LOGO)
        if logo.is_file(): clean['logo_path']=asset(logo,brand=not options.get('logo_path'))
        else:
            clean['render_settings']=json.loads(json.dumps(clean.get('render_settings') or {}))
            clean['render_settings']['outro_logo']={**clean['render_settings'].get('outro_logo',{}),'enabled':False}
        logo_enabled=(options.get('render_settings') or {}).get('outro_logo',{}).get('enabled',True)
        # Use the frozen engine's own constants for export validation; the exact
        # prepared dataclass and render options, not a re-planned timeline, run there.
        seconds=plan.duration+(engine.CTA_SECONDS if str(options.get('cta') or '').strip() else 0)
        seconds+=engine.LOGO_SECONDS if logo_enabled and logo.is_file() else 0
        fps=30
        if style=='talking_3':
            from fractions import Fraction
            from engine.localize import probe_fps
            cadence=Fraction(str(probe_fps(video)))
            if cadence.denominator!=1:
                return False # Preserve fractional-cadence legacy exports locally.
            fps=int(cadence)
        extra={}
        if style=='talking_3':
            extra['titles']=plan.titles
            for key in ('full_pictures','card_pictures'):
                extra[key]=[i for i,s in enumerate(plan.shots) if id(s) in getattr(plan,key,set())]
        (staged/'talking.json').write_text(json.dumps({'style':style,'video':source,'plan':plan_data,'options':clean,**extra},ensure_ascii=False))
        lock_root=Path(who[2][0])
        return render_prepared(staged,output,user=who[0],project_id=who[1],engine=style,entrypoint='talking.json',
                               duration=seconds,width=1080,height=1920,fps=fps,on_progress=on_progress,
                               should_cancel=who[3] if len(who)>3 else None,on_stage=who[4] if len(who)>4 else None, on_detail=who[5] if len(who)>5 else None,
                               lock_root=lock_root,audio_required=True)


def localize(video, state, placements, output, *, work_dir, fonts_dir=None, music=None, logo=None, on_progress=None, only_covers=False):
    """Localize's final composition: the source video, the dubbed voice clips, the caption/overlay plan and the music, rendered on a worker.
    Translation, voice generation and caption detection have already run on the server; only this ffmpeg composition leaves it."""
    if not eligible():
        return False
    import hashlib
    import shutil
    import tempfile
    from fractions import Fraction
    from engine import localize as engine
    from .service import render_prepared
    who = identity.get()
    root = Path(engine.__file__).resolve().parents[1]
    if fonts_dir is not None and Path(fonts_dir).resolve() != (root / 'presets/fonts').resolve():
        return False                      # the worker only has the library fonts
    cadence = Fraction(str(engine.probe_fps(video)))
    if cadence.denominator != 1:
        return False                      # fractional cadence keeps its local export
    with tempfile.TemporaryDirectory(prefix='editorgpt-localize-input-') as directory:
        staged = Path(directory)
        approved = [*(Path(p).resolve() for p in who[2]), (root / 'assets/music').resolve(), (root / 'assets/brand').resolve()]

        def asset(value):
            source = Path(value).resolve(strict=True)
            if not any(source.is_relative_to(base) for base in approved) or not source.is_file():
                raise ValueError('Localize asset is not owned or library-approved')
            name = 'assets/' + hashlib.sha256(str(source).encode()).hexdigest() + source.suffix
            (staged / 'assets').mkdir(exist_ok=True)
            shutil.copy2(source, staged / name)
            return name
        src_w, src_h, source_duration = engine.probe_video(video)
        width, height = engine.output_size(src_w, src_h)
        duration, _ = engine.output_timing(state, placements, source_duration)
        data = {'state': state, 'video': asset(video), 'only_covers': bool(only_covers),
                'placements': [{**p, 'file': asset(p['file'])} for p in placements],
                'music': asset(music) if music and Path(music).is_file() else None,
                'logo': asset(logo) if logo and Path(logo).is_file() else None}
        try:
            (staged / 'localize.json').write_text(json.dumps(data, ensure_ascii=False))
        except TypeError:
            return False
        return render_prepared(staged, output, user=who[0], project_id=who[1], engine='localize', entrypoint='localize.json',
                               duration=duration, width=width, height=height, fps=int(cadence), on_progress=on_progress,
                               should_cancel=who[3] if len(who) > 3 else None, on_stage=who[4] if len(who) > 4 else None,
                               on_detail=who[5] if len(who) > 5 else None, lock_root=Path(who[2][0]), audio_required=True)


def _library_panels(plan) -> bool:
    """True when any panel of the reel is filled from the panel library (or the page's own template) on the worker instead of a finished authored scene."""
    return any(seg.get("layout") == "split" and seg.get("beat") and not (seg["beat"].get("custom")) for seg in (plan.script or {}).get("segments", []))


def talking5(video, plan, output, *, work_dir, music, pack, fx, hook, on_progress=None):
    """Talking 5's heavy half: the two HyperFrames layers, the person matte, the face effects and the composition run on a worker. The model-written
    panels and the effect plan are already in `plan`/`fx`; the tscaps hook is a finished overlay file."""
    if not eligible():
        return False
    import dataclasses
    import hashlib
    import shutil
    import tempfile
    from engine.talking_styles import talking_1 as engine
    from .service import render_prepared
    who = identity.get()
    with tempfile.TemporaryDirectory(prefix='editorgpt-talking5-input-') as directory:
        staged = Path(directory)
        from engine.hyperframes.assets import cache_dir, ensure_gsap
        approved = [*(Path(p).resolve() for p in who[2]), (engine.PROJECT_ROOT / 'assets/music').resolve(), cache_dir().resolve()]

        def asset(value):
            source = Path(value).resolve(strict=True)
            if not any(source.is_relative_to(base) for base in approved) or not source.is_file():
                raise ValueError('Talking 5 asset is not owned or library-approved')
            name = 'assets/' + hashlib.sha256(str(source).encode()).hexdigest() + source.suffix
            (staged / 'assets').mkdir(exist_ok=True)
            shutil.copy2(source, staged / name)
            return name
        try:
            data = {'video': asset(video), 'plan': dataclasses.asdict(plan), 'script': plan.script, 'pack': pack.model_dump(mode='json'),
                    'sentences': plan.sentences, 'creative_plan': getattr(plan, 'creative_plan', None), 'fx': list(fx or []),
                    'music': asset(music) if music and Path(music).is_file() else None,
                    'hook': asset(hook) if hook and Path(hook).is_file() else None, 'gsap': asset(ensure_gsap())}
            (staged / 'talking5.json').write_text(json.dumps(data, ensure_ascii=False))
        except (TypeError, ValueError):
            return False                      # anything that cannot travel as plain data keeps its local render
        # A worker builds the panel layer with ITS OWN image's code: a panel that is not a finished authored scene is filled there from the panel library, whose components in the
        # image still load GSAP from a CDN that an offline worker never reaches (the render hangs). Until the worker image carries the fixed library such a reel renders on the server:
        # no profile has this feature, so the policy keeps it local.
        # RENDER_CLOUD_PANEL_LIBRARY=1 is set once the talking_5 worker image carries the offline-safe library (rebuilt 2026-11-12); without it such a reel stays local.
        gated = _library_panels(plan) and os.environ.get('RENDER_CLOUD_PANEL_LIBRARY', '').strip() != '1'
        features = (['face-effects'] if fx else []) + (['panel-library'] if gated else [])
        return render_prepared(staged, output, user=who[0], project_id=who[1], engine='talking_5', entrypoint='talking5.json',
                               duration=plan.duration, width=1080, height=1920, fps=30, on_progress=on_progress,
                               features=features,
                               should_cancel=who[3] if len(who) > 3 else None, on_stage=who[4] if len(who) > 4 else None,
                               on_detail=who[5] if len(who) > 5 else None, lock_root=Path(who[2][0]), audio_required=True)
