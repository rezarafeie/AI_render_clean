"""Shared render budget and owned-media admission for maintained motion templates."""
from __future__ import annotations

import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_SCENES, MAX_TOTAL_FRAMES, MAX_SCENE_FRAMES = 30, 2700, 900


def validate_motion_config(config: dict, job_dir: Path) -> dict:
    """Return a copy with canonical paths. Reject before preparation or rendering."""
    config = copy.deepcopy(config)
    root = job_dir.resolve()
    scenes = config.get('scenes', [])
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= MAX_SCENES:
        raise ValueError('Motion scene count is outside render limits')
    for scene in scenes:
        frames = scene.get('frames')
        if type(frames) is not int or not 1 <= frames <= MAX_SCENE_FRAMES:
            raise ValueError('Scene duration is outside render limits')
    if sum(s['frames'] for s in scenes) > MAX_TOTAL_FRAMES:
        raise ValueError('Motion duration exceeds 90 seconds')

    def owned(value, label):
        path = (root / value).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f'Invalid owned {label}')
        return str(path)

    for scene in scenes:
        if not scene.get('asset'):
            raise ValueError('Invalid owned scene asset')
        scene['asset'] = owned(scene['asset'], 'scene asset')
        if scene.get('narration'):
            scene['narration'] = owned(scene['narration'], 'scene narration')
        supporting = scene.get('supporting_assets', [])
        if not isinstance(supporting, list) or len(supporting) > 3:
            raise ValueError('Supporting asset count is outside render limits')
        scene['supporting_assets'] = [owned(item, 'supporting asset') for item in supporting]
    if config.get('music'):
        music = (root / config['music']).resolve()
        if not (music.is_relative_to(root) or music.is_relative_to((ROOT / 'assets/music').resolve())):
            raise ValueError('Music must belong to the job or approved library')
        if not music.is_file():
            raise ValueError('Music asset is missing')
        config['music'] = str(music)
    return config
