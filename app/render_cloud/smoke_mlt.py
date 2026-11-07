"""Render a synthetic MLT job through the standard worker and verify its result."""
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from .benchmark import measure
from .contracts import RenderSpec
from .parity import compare
from .prepare import freeze
from .settings import CloudSettings, object_store


def fixture(root, job, user, timeout, *, subtitles=False):
    width, height, seconds = (640, 360, 60) if subtitles else (320, 180, 3)
    end = seconds * 30 - 1
    media = root / 'test-source.mp4'
    subprocess.run([
        'ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=s={width}x{height}:r=30:d={seconds}',
        '-f', 'lavfi', '-i', f'sine=frequency=880:sample_rate=48000:duration={seconds}',
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(media),
    ], check=True, timeout=45)
    assets = ['test-source.mp4', 'test.mlt']
    subtitle_property = ''
    if subtitles:
        font = Path(__file__).resolve().parents[2] / 'presets/fonts/Vazirmatn-Regular.ttf'
        (root / 'fonts').mkdir()
        shutil.copyfile(font, root / 'fonts' / font.name)
        assets.extend(['captions.ass', f'fonts/{font.name}'])
        subtitle_property = ('<property name="ai-render:burn_ass">captions.ass</property>'
                             '<property name="ai-render:burn_ass_fontsdir">fonts</property>')
        lines = [
            '[Script Info]', 'ScriptType: v4.00+', f'PlayResX: {width}', f'PlayResY: {height}',
            '[V4+ Styles]',
            'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, '
            'Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, '
            'Alignment, MarginL, MarginR, MarginV, Encoding',
            'Style: Default,Vazirmatn,27,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,'
            '0,0,0,0,100,100,0,0,1,2,0,2,20,20,24,1',
            '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text',
        ]
        for second in range(seconds):
            lines.append(f'Dialogue: 0,0:00:{second:02d}.00,0:00:{second:02d}.92,Default,,0,0,0,,زیرنویس آزمایشی {second + 1}')
        (root / 'captions.ass').write_text('\n'.join(lines) + '\n')
    (root / 'test.mlt').write_text(
        f'<mlt producer="timeline"><profile width="{width}" height="{height}" frame_rate_num="30" '
        'frame_rate_den="1" progressive="1" sample_aspect_num="1" sample_aspect_den="1" '
        'display_aspect_num="16" display_aspect_den="9" colorspace="709"/>'
        f'{subtitle_property}<producer id="source" in="0" out="{end}"><property name="resource">test-source.mp4</property>'
        '<property name="mlt_service">avformat</property></producer>'
        f'<playlist id="timeline"><entry producer="source" in="0" out="{end}"/></playlist></mlt>'
    )
    return freeze(root, assets, job_id=job, user_id=user,
                  project_id='synthetic-mlt-canary', engine='mlt', entrypoint='test.mlt',
                  duration_seconds=seconds, fps=30, width=width, height=height, timeout_seconds=timeout,
                  workspace_bytes=128 * 1024**2, audio_required=True,
                  features=['subtitles'] if subtitles else [])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--cloud-user', help='Dedicated authorized synthetic benchmark identity')
    parser.add_argument('--max-hourly-usd', type=float)
    parser.add_argument('--subtitles', action='store_true', help='Use a 60-second Persian subtitle fixture')
    parser.add_argument('--export-fixture', type=Path)
    parser.add_argument('--prepared-fixture', type=Path)
    args = parser.parse_args()
    config = CloudSettings().effective()
    if args.cloud_user and (not args.max_hourly_usd or not args.cloud_user.startswith('synthetic-')):
        parser.error('Cloud mode requires a synthetic identity and a positive hourly price ceiling')
    if args.prepared_fixture and (not args.cloud_user or args.export_fixture or args.subtitles):
        parser.error('A prepared fixture is an input to cloud mode')
    job = uuid.uuid4().hex
    args.report.parent.mkdir(parents=True, exist_ok=True)
    result = {'job_id': job}
    with tempfile.TemporaryDirectory(prefix='editorgpt-smoke-') as tmp:
        root = Path(tmp)
        if args.prepared_fixture:
            root = args.prepared_fixture.resolve()
            original = RenderSpec.model_validate_json((root / 'fixture.json').read_text())
            reference = json.loads((root / 'reference.json').read_text())
            if original.project_id != 'synthetic-mlt-canary' or original.engine != 'mlt' or (
                reference['manifest_sha256'] != hashlib.sha256(original.model_dump_json().encode()).hexdigest()
            ):
                raise ValueError('Prepared fixture reference does not match')
            result['local'] = reference
            spec = original.model_copy(update={'job_id': job, 'user_id': args.cloud_user,
                                               'timeout_seconds': min(180, config.max_wall_seconds)})
        else:
            spec = fixture(root, job, args.cloud_user or 'synthetic-local', min(180, config.max_wall_seconds),
                           subtitles=args.subtitles)
            if args.export_fixture:
                args.export_fixture.mkdir(parents=True)
                for asset in spec.assets:
                    target = args.export_fixture / asset.path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(root / asset.path, target)
                (args.export_fixture / 'fixture.json').write_text(spec.model_dump_json())
            local = args.report.parent / (job + '-local.mp4')
            result['local'] = measure(spec, root, local, 'local')
            if args.export_fixture:
                (args.export_fixture / 'reference.json').write_text(json.dumps(result['local']))
                shutil.copy2(local, args.export_fixture / 'reference.mp4')
        if args.cloud_user:
            store = object_store(config)
            try:
                output = args.report.parent / (job + '-cloud.mp4')
                result['cloud'] = measure(spec, root, output, 'runpod_cpu',
                                          allow_paid=True, max_hourly=args.max_hourly_usd)
                result['metadata_comparison'] = compare(result['local']['media'], result['cloud']['media'])
            finally:
                # This CLI requires a dedicated synthetic identity. No customer keys
                # are enumerated or deleted, even when the smoke job fails.
                prefix = store.prefix(args.cloud_user)
                for name in ('bootstrap.json', 'status.json', 'control.json', 'candidate.mp4'):
                    store.client.delete_object(Bucket=store.bucket, Key=f'{prefix}jobs/{job}/{name}')
                for asset in spec.assets:
                    store.client.delete_object(Bucket=store.bucket, Key=store.key(spec.user_id, asset.sha256))
    args.report.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
