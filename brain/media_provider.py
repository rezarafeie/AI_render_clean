"""Provider-neutral media generation adapter with registry and local fixture provider."""
from __future__ import annotations

import hashlib
import io
import logging
import math
import os
import random
import subprocess
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)
IMAGE_ATTEMPTS = 1  # Paid generation is never retried without explicit user confirmation.
from .lm_gateway import observe_specialized


@dataclass
class MediaResult:
    file_path: str
    source: str
    cost_usd: Optional[float] = 0.0
    metadata: dict = field(default_factory=dict)
    generation_id: str = ""
    width: int = 0
    height: int = 0
    duration_s: float = 0.0
    fps: int = 0


class ProviderAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def generate_image(self, prompt: str, aspect: str, output_dir: Path) -> MediaResult:
        ...

    @abstractmethod
    def generate_video(self, prompt: str, duration: float, aspect: str, output_dir: Path) -> MediaResult:
        ...

    @property
    def capabilities(self) -> list[str]:
        return ["image", "video"]

    @property
    def has_key(self) -> bool:
        key_var = f"CONTENT_PROVIDER_{self.name.upper()}_KEY"
        return bool(os.environ.get(key_var))


def _retry_with_backoff(fn, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            if attempt == max_retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            log.warning("attempt %d failed (%s), retrying in %.1fs", attempt + 1, exc, wait)
            time.sleep(wait)


def _parse_resolution(aspect: str) -> tuple[int, int]:
    mapping = {
        "9:16": (1080, 1920),
        "1:1": (1080, 1080),
        "16:9": (1920, 1080),
        "4:5": (1080, 1350),
    }
    return mapping.get(aspect, (1080, 1920))


def still_to_motion_video(
    image_path: Path,
    output_dir: Path,
    duration: float,
    aspect: str,
    *,
    generation_id: str = "",
    cost_usd: Optional[float] = 0.0,
    source: str = "image_motion",
    metadata: Optional[dict] = None,
) -> MediaResult:
    """Turn a generated still into a bounded, editable H.264 timeline source."""
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) \
            or not math.isfinite(duration) or duration <= 0:
        raise ValueError("video duration must be a positive finite number")
    still = Path(image_path)
    if not still.is_file():
        raise FileNotFoundError(f"image source not found: {still}")
    duration_s = min(float(duration), 30.0)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generation_id = generation_id or uuid.uuid4().hex[:12]
    width, height = _parse_resolution(aspect)
    fps = 30
    frames = max(1, round(duration_s * fps))
    out_path = output_dir / f"motion_{generation_id}.mp4"
    zoom_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0xf4f4f1,"
        f"zoompan=z='min(1+0.0002*on,1.08)':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={width}x{height}:fps={fps},format=yuv420p"
    )
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(still),
        "-vf", zoom_filter, "-frames:v", str(frames),
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-movflags", "+faststart", str(out_path),
    ], capture_output=True, check=True, timeout=max(60, round(duration_s * 12)))
    return MediaResult(
        file_path=str(out_path),
        source=source,
        cost_usd=cost_usd,
        generation_id=generation_id,
        width=width,
        height=height,
        duration_s=round(frames / fps, 3),
        fps=fps,
        metadata={**(metadata or {}), "still_path": str(still), "motion": "subtle_zoompan"},
    )


class LocalFixtureProvider(ProviderAdapter):
    """Generates placeholder colored frames/video with ffmpeg. No API keys needed."""

    name = "local_fixture"

    @property
    def has_key(self) -> bool:
        return True

    def generate_image(self, prompt: str, aspect: str, output_dir: Path) -> MediaResult:
        w, h = _parse_resolution(aspect)
        gen_id = uuid.uuid4().hex[:12]
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"fixture_{gen_id}.png"

        color = "#{:06x}".format(random.randint(0x222222, 0xCCCCCC))
        label = prompt[:40].replace("'", "").replace('"', "")

        def _gen():
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}:d=1",
                "-vf", f"drawtext=text='{label}':fontsize=36:fontcolor=white:x=(w-tw)/2:y=(h-th)/2",
                "-frames:v", "1",
                str(out_path),
            ], capture_output=True, check=True, timeout=15)

        try:
            _retry_with_backoff(_gen, max_retries=2)
        except Exception:
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}:d=1",
                "-frames:v", "1",
                str(out_path),
            ], capture_output=True, check=True, timeout=15)

        return MediaResult(
            file_path=str(out_path),
            source="local_fixture",
            cost_usd=0.0,
            generation_id=gen_id,
            width=w, height=h,
            duration_s=0.0, fps=0,
            metadata={"prompt": prompt, "color": color},
        )

    def generate_video(self, prompt: str, duration: float, aspect: str, output_dir: Path) -> MediaResult:
        w, h = _parse_resolution(aspect)
        gen_id = uuid.uuid4().hex[:12]
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"fixture_{gen_id}.mp4"
        fps = 30

        color = "#{:06x}".format(random.randint(0x222222, 0xCCCCCC))
        dur = max(0.5, min(duration, 30.0))

        def _gen():
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i",
                f"color=c={color}:s={w}x{h}:d={dur}:r={fps}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-t", str(dur),
                str(out_path),
            ], capture_output=True, check=True, timeout=60)

        _retry_with_backoff(_gen, max_retries=3)

        return MediaResult(
            file_path=str(out_path),
            source="local_fixture",
            cost_usd=0.0,
            generation_id=gen_id,
            width=w,
            height=h,
            duration_s=round(dur, 2),
            fps=fps,
            metadata={"prompt": prompt, "color": color},
        )


_registry: dict[str, ProviderAdapter] = {}


def register_provider(name: str, adapter: ProviderAdapter) -> None:
    adapter.name = name
    _registry[name] = adapter


def get_provider(name: str) -> ProviderAdapter:
    """Images come from the AI router (its image routes) or, in tests, the local fixture: there is no direct provider."""
    if name != "local_fixture":
        from .lm_gateway import configured
        if not configured():
            raise RuntimeError("The AI router is not configured; no image was requested")
        name = 'lm_gateway'
    if name not in _registry:
        raise KeyError(f"unknown provider: {name!r}. registered: {list(_registry.keys())}")
    return _registry[name]


def list_providers() -> list[dict]:
    return [
        {"name": name, "capabilities": adapter.capabilities,
         "has_key": adapter.has_key, "key_configured": adapter.has_key}
        for name, adapter in _registry.items()
    ]


class GatewayImageProvider(ProviderAdapter):
    name='lm_gateway'

    @property
    def has_key(self):
        from .lm_gateway import configured, defaults
        return configured() and bool(defaults().get('photorealistic_image',{}).get('enabled'))

    @property
    def capabilities(self):
        return ['image','motion_video_from_image']

    def generate_image(self,prompt,aspect,output_dir):
        from .lm_gateway import complete
        import base64
        response,record=complete('photorealistic_image',prompt,endpoint='image',required={'image'},extra={'n':1,'size':'1024x1024'})
        item=(response.get('data') or [{}])[0]
        encoded=item.get('b64_json','')
        if not encoded or len(encoded)>40*1024*1024:
            raise RuntimeError('Gateway did not return a bounded inline image; no duplicate generation was submitted')
        raw=base64.b64decode(encoded,validate=True)
        from PIL import Image
        image=Image.open(io.BytesIO(raw))
        if max(image.size)>8192 or image.width*image.height>32_000_000:
            raise ValueError('Generated image dimensions exceed safety limits')
        image.load()
        output_dir.mkdir(parents=True,exist_ok=True)
        path=output_dir/f'gateway_{uuid.uuid4().hex[:12]}.png'
        image.convert('RGB').save(path)
        return MediaResult(file_path=str(path),source='lm_gateway_image',cost_usd=record.get('cost'),
                           width=image.width,height=image.height,generation_id=path.stem,
                           metadata={'model':response.get('model'),'requested_model':record.get('requested_model'),'aspect':aspect})

    def generate_video(self,prompt,duration,aspect,output_dir):
        still=self.generate_image(prompt,aspect,output_dir)
        return still_to_motion_video(still.file_path,output_dir,duration,aspect,generation_id=still.generation_id,
                                     cost_usd=still.cost_usd,source='lm_gateway_image_motion',metadata=still.metadata)


register_provider('lm_gateway',GatewayImageProvider())
register_provider("local_fixture", LocalFixtureProvider())
