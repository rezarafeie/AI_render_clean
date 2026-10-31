"""Typed native Shotcraft adapter over the existing Remotion renderer.

Bounded reviewed components only. No request-time installs, generated source,
arbitrary paths, external media, provider requests or title-only fallbacks.
"""
import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal, Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator, TypeAdapter
from .shotcraft_card_flip import CardFlipNative, reading_frames as card_reading_frames
from .shotcraft_compare import BeforeAfterNative,validate_assets as comparison_assets

ROOT = Path(__file__).resolve().parents[1]
REVISION = "5a2e98daade313c4f376120f38427eb19a108e8c"
DIMS = {"vertical":(1080,1920),"horizontal":(1920,1080),"square":(1080,1080)}


class ShotcraftNative(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_id: Literal["shotcraft:bezier-source-converge-merge"]
    caption: str = Field(min_length=1,max_length=48)
    source_icons: tuple[Literal["shot","card","code","wave"], ...] = Field(min_length=4,max_length=4)
    output_icon: Literal["check","play","spark"] = "play"
    accent: str = Field(default="#5b63d3",pattern=r"^#[0-9a-fA-F]{6}$")
    locale: Literal["fa-IR","en-US"] = "fa-IR"

    @field_validator("caption")
    @classmethod
    def plain_bounded_caption(cls,value):
        if not value.strip() or len(value.encode("utf-16-le",errors="surrogatepass"))//2>48 or any(c in value for c in "<>"):
            raise ValueError("Use a nonempty bounded plain caption")
        if len(value.split())>8:
            raise ValueError("Use at most eight complete caption words")
        return value.strip()


class TextColumnNative(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_id: Literal["shotcraft:text-column-converge"]
    caption: str = Field(min_length=1,max_length=24)
    prefix: str = Field(min_length=1,max_length=12)
    features: tuple[str,...] = Field(min_length=2,max_length=6)
    subtitle: str = Field(min_length=1,max_length=48)
    locale: Literal["fa-IR","en-US"] = "fa-IR"

    @field_validator("caption","prefix","subtitle")
    @classmethod
    def plain_text(cls,value,info):
        limit={"caption":24,"prefix":12,"subtitle":48}[info.field_name]
        if not value.strip() or len(value.encode("utf-16-le",errors="surrogatepass"))//2>limit or any(c in value for c in "<>\n\r"):
            raise ValueError("Use explicit single-line plain text")
        return value.strip()

    @field_validator("features")
    @classmethod
    def bounded_features(cls,values):
        for value in values:
            if not value.strip() or len(value.encode("utf-16-le",errors="surrogatepass"))//2>24 or len(value.split())>3 or any(c in value for c in "<>\n\r"):
                raise ValueError("Features require 1–24 plain characters and at most three words")
        if len(set(v.strip() for v in values))!=len(values):
            raise ValueError("Do not repeat feature phrases")
        return tuple(v.strip() for v in values)


NativeSpec = Annotated[ShotcraftNative | TextColumnNative | CardFlipNative | BeforeAfterNative, Field(discriminator="resource_id")]


def parse_spec(value):
    return TypeAdapter(NativeSpec).validate_python(value)


class ShotcraftMount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec: NativeSpec
    instance: str = Field(pattern=r"^s[1-8]-shotcraft$")
    start: float = Field(ge=0,le=60,allow_inf_nan=False)
    duration: float = Field(ge=4,le=12,allow_inf_nan=False)
    format: Literal["vertical","horizontal","square"]
    asset: str | None = Field(default=None,pattern=r"^assets/s[1-8]-shotcraft-[0-9a-f]{16}\.mp4$")

    @model_validator(mode="after")
    def supported_stage(self):
        if isinstance(self.spec,(TextColumnNative,CardFlipNative,BeforeAfterNative)) and self.format!="horizontal":
            raise ValueError("Selected native component requires the horizontal stage")
        if self.duration<required_seconds(self.spec):
            raise ValueError("Native scene omits its required reading hold")
        return self


def catalog():
    def compact(value):
        if isinstance(value,dict): return {k:compact(v) for k,v in value.items() if k!="title"}
        if isinstance(value,list): return [compact(v) for v in value]
        return value
    return [{"id":"shotcraft:bezier-source-converge-merge", "field":"shotcraft_component",
             "execution":"pinned original Remotion source, embedded as a framework-owned local clip",
             "best_for":"Four screenshot/card/code/audio sources merging into one result; a convergence diagram, not a substitute for unrelated explanatory imagery.",
             "inputs":compact(ShotcraftNative.model_json_schema()), "seconds":[4,12],
             "constraints":"Caption equals approved headline, <=8 words; seconds >= max(4,2.4+max(1.2,words/2.5)). Safe icons only, no URLs/code/assets. Original source executes through existing Remotion → HyperFrames. No fallback."},
            {"id":"shotcraft:text-column-converge","field":"shotcraft_component","format":"horizontal",
             "best_for":"Feature phrases rotate at fixed opposing edges, then converge ONCE into prefix + approved headline; not explanatory imagery or a full film.",
             "inputs":compact(TextColumnNative.model_json_schema()),"seconds":[4,12],
             "constraints":"Caption equals approved headline. Features <=3 words each; <=24 UTF16 units each. Reading frames=sum(ceil(max(.6,feature_words/2.5)*30)+[0,3,1,2,0,3][i])+68+max(36,ceil(subtitle_words/2.5*30)); duration >=max(4,frames/30). Local shaped font measurement rejects copy exceeding the original 660px title or 900px subtitle slots. No automatic clipping, provider switch or fallback."},
            {"id":"shotcraft:card-flip-reveal","field":"shotcraft_component","format":"horizontal",
             "best_for":"Exactly three feature → measured result pairs, original staggered 3D cards with lighting/reflection. Abstract summaries, NOT screenshots or a full explainer.",
             "inputs":compact(CardFlipNative.model_json_schema()),"seconds":[4,12],
             "constraints":"Use ONLY user-provided verified numbers with an evidence reference per card; never invent metrics. Caption=approved headline. Short single-line copy: measured widths reject overflow (header1480px/84px, name400/52, description and front lines400/40, result400/40, value370/120). Duration frames>=max(60,ceil(densest_front_words/2.5*30))+50+max(40,ceil(densest_back_words/2.5*30)); front=name+description+3lines; back=name+result_label+before_label+after_label+unit. No clipping, code, URLs or fallback."},
            {"id":"shotcraft:before-after-slider-scrub","field":"shotcraft_component","format":"horizontal",
             "best_for":"Two actual user-supplied states of the same view. Original fast fling, bounce and slow comparison slider. Never fabricate or degrade before.",
             "inputs":compact(BeforeAfterNative.model_json_schema()),"seconds":[5,12],
             "constraints":"Caption=approved headline; header width1640px at64px, labels280px at40px measured. Select ONLY listed eligible owned assets, two different opaque SDR PNG images of identical16:9 dimensions,1920x1080–3840x2160. Same camera/layout and before/after roles must be specified by user; ask if unknown. comparison_basis records user-supplied basis, not proof of improvement. No URLs, paths outside listed assets, automatic enhancement, clipping or fallback. Images fit fully in reserved body; slider reaches40% then holds."}]


def feature_frames(spec):
    return [math.ceil(max(.6,len(v.split())/2.5)*30)+[0,3,1,2,0,3][i] for i,v in enumerate(spec.features)]


def required_seconds(spec):
    if isinstance(spec,BeforeAfterNative):return 5
    if isinstance(spec,CardFlipNative):
        return max(4,card_reading_frames(spec)/30)
    if isinstance(spec,TextColumnNative):
        return max(4,(sum(feature_frames(spec))+10+36+18+4+max(36,math.ceil(len(spec.subtitle.split())/2.5*30)))/30)
    return max(4,2.4+max(1.2,len(spec.caption.split())/2.5))


def source_fingerprint():
    from .shotcraft import manifest, read_reference
    data = manifest()
    # Exact upstream source and all shared fixtures must match before execution.
    for name in data["sha256"]:
        read_reference(name,data)
    runtime = json.loads((ROOT/"creative/shotcraft_data/runtime_sha256.json").read_text())
    if runtime["revision"] != REVISION:
        raise ValueError("Unreviewed Shotcraft runtime revision")
    for name,expected in runtime["sha256"].items():
        path = (ROOT/"creative/shotcraft_data"/name).resolve()
        if not path.is_relative_to((ROOT/"creative/shotcraft_data").resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError("Shotcraft dependency integrity failure")
    adapter_files = [Path(__file__),ROOT/"remotion/shotcraft-content-loader.cjs",ROOT/"remotion/shotcraft-native-config.mjs",
                     ROOT/"remotion/shotcraft-text-loader.cjs",ROOT/"remotion/src/shotcraft/useTextMetrics.ts",
                     ROOT/"creative/shotcraft_card_flip.py",ROOT/"remotion/shotcraft-card-loader.cjs",ROOT/"remotion/src/shotcraft/useCardMetrics.ts",
                     ROOT/"creative/shotcraft_compare.py",ROOT/"remotion/shotcraft-compare-loader.cjs",ROOT/"remotion/src/shotcraft/useCompareMetrics.ts",
                     ROOT/"remotion/src/shotcraft-native.tsx",ROOT/"remotion/src/shotcraft/FrameReady.tsx",ROOT/"remotion/render.mjs",
                     ROOT/"engine/remotion_renderer.py",ROOT/"presets/fonts/Vazirmatn-Regular.ttf"]
    return hashlib.sha256(json.dumps({"source":data["sha256"],"runtime":runtime["sha256"],
        "adapter":[hashlib.sha256(p.read_bytes()).hexdigest() for p in adapter_files]},sort_keys=True).encode()).hexdigest()


def inspect_output(path, width, height, seconds):
    result = subprocess.run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(path)],
                            capture_output=True,text=True,timeout=20,check=True)
    data = json.loads(result.stdout)
    video = next(s for s in data["streams"] if s["codec_type"]=="video")
    duration = float(data["format"]["duration"])
    if (video["width"],video["height"]) != (width,height) or video["codec_name"]!="h264" or abs(duration-seconds)>.1:
        raise ValueError("Native component output does not match the approved stage or duration")
    keyframes = subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-skip_frame","nokey","-show_frames",
                               "-show_entries","frame=best_effort_timestamp_time","-of","json",str(path)],
                              capture_output=True,text=True,timeout=20,check=True)
    times = [float(f["best_effort_timestamp_time"]) for f in json.loads(keyframes.stdout)["frames"] if "best_effort_timestamp_time" in f]
    if not times or times[0]>.05:
        raise ValueError("Native component is missing its initial keyframe")
    interval = max([b-a for a,b in zip(times,times[1:])]+[duration-times[-1]])
    if interval>1.1 or video.get("pix_fmt")!="yuv420p":
        raise ValueError("Native component must use seek-safe one-second keyframes and yuv420p")
    return {"width":width,"height":height,"duration":duration,"codec":"h264","max_keyframe_interval":interval}


def materialize(project: Path, spec: NativeSpec, instance: str, duration: float, format: str, *, on_progress=None):
    if not re.fullmatch(r"s[1-8]-shotcraft",instance) or format not in DIMS or not math.isfinite(duration) or not required_seconds(spec)<=duration<=12:
        raise ValueError("Unsupported native Shotcraft instance, format or duration")
    # Revalidate even model_copy/update values before crossing the process boundary.
    spec = parse_spec(spec.model_dump())
    if isinstance(spec,(TextColumnNative,CardFlipNative,BeforeAfterNative)) and format!="horizontal":
        raise ValueError("Selected native source currently requires its horizontal design stage")
    if on_progress: on_progress(0)
    root = project.resolve()
    paths,digests=comparison_assets(root,spec) if isinstance(spec,BeforeAfterNative) else ([],[])
    source = source_fingerprint()
    width,height = DIMS[format]
    frames = round(duration*30)
    fingerprint = hashlib.sha256(json.dumps({"spec":spec.model_dump(),"frames":frames,"format":format,"source":source,**({"input_sha256":digests} if digests else {})},
                                           ensure_ascii=True,sort_keys=True).encode()).hexdigest()
    stem = instance+"-"+fingerprint[:16]
    output,partial,receipt = [root/"assets"/(stem+suffix) for suffix in (".mp4",".part.mp4",".json")]
    for target in (output,partial,receipt,partial.with_suffix(".remotion.json")):
        if not target.resolve().is_relative_to(root):
            raise ValueError("Native component output escapes the owned project")
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.is_file() and receipt.is_file():
        try:
            cached = json.loads(receipt.read_text())
            if cached.get("fingerprint")==fingerprint and cached.get("artifact_sha256")==hashlib.sha256(output.read_bytes()).hexdigest():
                inspect_output(output,width,height,frames/30)
                if on_progress: on_progress(100)
                return cached
        except (OSError,ValueError,subprocess.SubprocessError):
            pass  # A corrupt cache is not a valid completed operation.
    from engine.remotion_renderer import render
    render({"version":3,"width":width,"height":height,"scenes":[{"frames":frames,"kind":"shotcraft_native","shotcraft":spec.model_dump(),**({"supporting_assets":[str(p.relative_to(root)) for p in paths]} if paths else {})}]},
           partial,job_dir=root,on_progress=on_progress,timeout=600)
    media = inspect_output(partial,width,height,frames/30)
    partial.replace(output)
    notice = root/"assets/SHOTCRAFT-LICENSE.txt"
    if not notice.resolve().is_relative_to(root):
        raise ValueError("Native component license path escapes project")
    shutil.copy2(ROOT/"creative/shotcraft_data/LICENSE",notice)
    record = {"resource_id":spec.resource_id,"instance":instance,"integration":"native-shotcraft-code",
              "source_revision":REVISION,"source_adapter_sha256":source,"fingerprint":fingerprint,
              "asset":output.relative_to(root).as_posix(),"artifact_sha256":hashlib.sha256(output.read_bytes()).hexdigest(),
              "media":media,"encoded_output_verified":True,"visual_review_verified":False}
    if digests:record['input_sha256']=digests
    receipt.write_text(json.dumps(record,ensure_ascii=False,indent=2))
    if on_progress: on_progress(100)
    return record
