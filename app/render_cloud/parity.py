"""Objective output metadata comparison for the benchmark gate, not visual QC."""
from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path


def probe(path: Path) -> dict:
    result = subprocess.run(['ffprobe', '-v', 'error', '-count_packets', '-show_streams',
                             '-show_format', '-of', 'json', str(path.resolve())],
                            capture_output=True, timeout=600, check=False)
    if result.returncode or len(result.stdout) > 1024 * 1024:
        raise ValueError('Output media could not be probed')
    data = json.loads(result.stdout)
    video = next((s for s in data['streams'] if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')), None)
    audio = next((s for s in data['streams'] if s.get('codec_type') == 'audio'), None)
    if video is None:
        raise ValueError('Output video stream missing')
    return {'width': int(video['width']), 'height': int(video['height']),
            'fps': str(Fraction(video['avg_frame_rate'])),
            # One packet per video frame in these encodes: counting packets reads the container only, counting decoded frames of a
            # several-hundred-megabyte reel took longer than the probe's limit on a busy server.
            'frames': int(video.get('nb_read_packets') or video.get('nb_read_frames') or 0),
            'duration': float(video.get('duration') or data['format']['duration']),
            'video_start': float(video.get('start_time', 0)),
            'audio_duration': float(audio.get('duration') or data['format']['duration']) if audio else None,
            'audio_start': float(audio.get('start_time', 0)) if audio else None}


def compare(reference: dict, candidate: dict) -> dict:
    differences = [key for key in ('width', 'height', 'fps', 'frames') if reference[key] != candidate[key]]
    tolerance = 1 / float(Fraction(reference['fps']))
    for key in ('duration', 'video_start', 'audio_duration', 'audio_start'):
        a, b = reference[key], candidate[key]
        if (a is None) != (b is None) or (a is not None and b is not None and abs(a - b) > tolerance):
            differences.append(key)
    return {'metadata_parity': not differences, 'differences': differences,
            'not_checked': ['decoded frame appearance', 'perceptual audio quality', 'subtitle layout',
                            'narration alignment to semantic events']}
