"""Render only motion windows in Chromium, then splice into the native cut.

Frame-quantized, high-quality sequential intermediates bound decoder memory and
retain the original audio outside motion windows. No model/provider calls.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path

from engine.probe import probe
from engine.talking_styles.talking_1 import cached_shot, shot_concat
from .schema import VisualBeat

FPS = 30


def motion_windows(beats: list[VisualBeat], total_frames: int) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    for beat in sorted(beats, key=lambda b: b.start):
        start = max(0, math.floor(beat.start * FPS) - 8)
        end = min(total_frames, math.ceil(beat.end * FPS) + 8)
        if end <= start:
            continue
        if windows and start <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(end, windows[-1][1]))
        else:
            windows.append((start, end))
    return windows


def _piece(source: Path, start: int, end: int, work: Path) -> Path:
    duration = (end-start)/FPS
    return cached_shot(['-threads','1','-ss',f'{start/FPS:.9f}','-i',str(source)], [
        f'[0:v]trim=duration={duration:.9f},setpts=PTS-STARTPTS,fps={FPS},'
        f'tpad=stop_mode=clone:stop_duration=0.1,trim=end_frame={end-start},setsar=1,format=yuv420p[v0]',
        f'[0:a]atrim=duration={duration:.9f},asetpts=PTS-STARTPTS[a0]',
    ], 0, duration, work)


def _join(clips: list[tuple[Path, float]], output: Path, work: Path) -> None:
    temporary = output.with_name(output.stem+'.partial.mp4')
    subprocess.run(['ffmpeg','-hide_banner','-v','error','-y',
        *shot_concat(clips, work), '-map','0:v:0','-map','0:a:0',
        '-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000',
        '-movflags','+faststart',str(temporary)], check=True, capture_output=True, timeout=300)
    temporary.replace(output)


def restore_continuous_audio(output: Path, source: Path, beats: list[VisualBeat], project: Path, duration: float) -> None:
    """Avoid AAC/segment priming drift: keep one continuous source audio clock."""
    from engine.sfx import cues_for, GAIN
    command = ['ffmpeg','-hide_banner','-v','error','-y','-i',str(output),'-i',str(source)]
    filters = ['[1:a]aresample=48000,asetpts=PTS-STARTPTS,apad,atrim=duration='+str(duration)+'[base]']
    labels = ['[base]']
    for time, name in cues_for(beats):
        path = project/'assets/sfx'/f'{name}.wav'
        if not path.is_file() or time >= duration:
            continue
        index = len(labels)+1
        command += ['-i',str(path)]
        label = f'sound{index}'
        filters.append(f'[{index}:a]aresample=48000,volume={GAIN[name]},adelay={round(time*48000)}S:all=1[{label}]')
        labels.append(f'[{label}]')
    filters.append(''.join(labels)+f'amix=inputs={len(labels)}:normalize=0:duration=first[audio]')
    temporary = output.with_name(output.stem+'.audio-fixed.mp4')
    command += ['-filter_complex_threads','1','-filter_complex',';'.join(filters),
        '-map','0:v:0','-map','[audio]','-c:v','copy','-c:a','aac','-b:a','192k',
        '-t',str(duration),'-movflags','+faststart',str(temporary)]
    subprocess.run(command,check=True,capture_output=True,timeout=300)
    temporary.replace(output)


def render_sparse(project: Path, output: Path, render_clip, *, on_progress=None, should_cancel=None) -> Path | None:
    meta_path = project/'meta.json'
    if not meta_path.is_file():
        return None
    meta = json.loads(meta_path.read_text())
    if meta.get('id') != 'ai-render-talking-2' or float(meta.get('duration',0)) < 40:
        return None
    beats = [VisualBeat.model_validate(b) for b in meta.get('visual_library', [])]
    total = round(float(meta['duration'])*FPS)
    windows = motion_windows(beats, total)
    active_frames = sum(end-start for start,end in windows)
    if not windows or active_frames >= total*.55:
        return None
    source = (project/'assets/base.mp4').resolve()
    facts = probe(source)
    if not any(s.get('codec_type') == 'audio' for s in facts['streams']):
        return None
    from .renderer import audit_key
    key = hashlib.sha256(audit_key(project).encode() +
        repr((str(source),source.stat().st_size,source.stat().st_mtime_ns,windows,'sparse-v1')).encode()).hexdigest()[:20]
    from .scratch import scratch_dir
    root = scratch_dir(project, 'hyperframes_sparse')/key
    root.mkdir(parents=True, exist_ok=True)

    def checkpoint():
        if should_cancel and should_cancel():
            raise RuntimeError('HyperFrames render canceled')

    compacted = root/'motion-source.mp4'
    clips = []
    mapping = []
    cursor = 0
    for index,(start,end) in enumerate(windows):
        checkpoint()
        piece = _piece(source,start,end,root/'motion-source')
        clips.append((piece,(end-start)/FPS))
        mapping.append((start,end,cursor,cursor+end-start))
        cursor += end-start
        if on_progress:
            on_progress(86+int(2*(index+1)/len(windows)))
    if not compacted.is_file():
        _join(clips,compacted,root/'motion-source')
    compact_beats = []
    for beat in beats:
        for start,end,local_start,_ in mapping:
            if start/FPS <= beat.start and end/FPS >= beat.end:
                clone = beat.model_copy(deep=True)
                delta = (start-local_start)/FPS
                clone.start -= delta
                clone.end -= delta
                compact_beats.append(clone)
                break
    if len(compact_beats) != len(beats):
        raise ValueError('Sparse motion mapping did not preserve every beat')
    compact_project = root/'composition'
    # Installed, approved registry blocks can reference their own local assets.
    for folder in ('assets','compositions'):
        if (project/folder).is_dir():
            shutil.copytree(project/folder,compact_project/folder,dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('base.mp4'))
    from .builder import build_project
    build_project(compact_project,compacted,compact_beats,duration=cursor/FPS,enable_registry=False)
    motion = root/'motion-render.mp4'
    if not motion.is_file():
        checkpoint()
        render_clip(compact_project,motion)
    motion_facts = probe(motion)
    if abs(float(motion_facts['format']['duration'])-cursor/FPS) > .12:
        raise ValueError('Sparse motion output duration differs from its frame map')
    final_clips = []
    source_cursor = 0
    for index,(start,end,local_start,local_end) in enumerate(mapping):
        checkpoint()
        if start > source_cursor:
            piece = _piece(source,source_cursor,start,root/'final')
            final_clips.append((piece,(start-source_cursor)/FPS))
        piece = _piece(motion,local_start,local_end,root/'final')
        final_clips.append((piece,(end-start)/FPS))
        source_cursor = end
        if on_progress:
            on_progress(92+int(6*(index+1)/len(mapping)))
    if source_cursor < total:
        checkpoint()
        piece = _piece(source,source_cursor,total,root/'final')
        final_clips.append((piece,(total-source_cursor)/FPS))
    _join(final_clips,output,root/'final')
    restore_continuous_audio(output,source,beats,project,total/FPS)
    result = probe(output)
    if abs(float(result['format']['duration'])-total/FPS) > .12:
        raise ValueError('Sparse final output duration differs from the original timeline')
    (root/'frame-map.json').write_text(json.dumps({'original_frames':total,'browser_frames':cursor,'windows':mapping},indent=2))
    return output
