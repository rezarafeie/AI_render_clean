"""Owned, explicit before/after images; never fabricate the 'before' state."""
import hashlib
import io
import re
import shutil
from pathlib import Path
from typing import Literal

from PIL import Image,ImageOps
from pydantic import BaseModel,ConfigDict,Field,field_validator
from .shotcraft_card_flip import plain

MAX_BYTES=16*1024*1024
ASSET=r"^assets/compare-[0-9a-f]{64}\.png$"


class BeforeAfterNative(BaseModel):
    model_config=ConfigDict(extra="forbid")
    resource_id:Literal['shotcraft:before-after-slider-scrub']
    caption:str=Field(min_length=1,max_length=48)
    before_label:str=Field(min_length=1,max_length=12)
    after_label:str=Field(min_length=1,max_length=12)
    before_asset:str=Field(pattern=ASSET)
    after_asset:str=Field(pattern=ASSET)
    comparison_basis:str=Field(min_length=1,max_length=160)
    locale:Literal['fa-IR','en-US']='fa-IR'

    @field_validator('caption','before_label','after_label','comparison_basis')
    @classmethod
    def bounded_copy(cls,value,info):
        return plain(value,{'caption':48,'before_label':12,'after_label':12,'comparison_basis':160}[info.field_name])


def canonical_image(raw):
    """Bounded opaque SDR screenshots only; strip metadata, honor orientation."""
    if not raw or len(raw)>MAX_BYTES:raise ValueError('Comparison image size exceeds limits')
    with Image.open(io.BytesIO(raw)) as image:
        if image.format not in {'PNG','JPEG'} or image.mode not in {'RGB','RGBA','L'} or getattr(image,'n_frames',1)!=1:
            raise ValueError('Comparison requires a static opaque PNG/JPEG SDR image')
        width,height=image.size
        if width>3840 or height>3840 or width*height>3840*2160:
            raise ValueError('Comparison image dimensions exceed limits')
        image=ImageOps.exif_transpose(image)
        if image.width*9!=image.height*16 or image.width<1920 or image.height<1080:
            raise ValueError('Comparison requires matching 16:9 images, at least 1920x1080')
        # RGB/L PNGs may carry tRNS transparency without an alpha channel.
        if image.convert('RGBA').getchannel('A').getextrema()!=(255,255):
            raise ValueError('Transparent comparison images are unsupported')
        output=io.BytesIO()
        profile=image.info.get('icc_profile')
        if profile and (not isinstance(profile,bytes) or len(profile)>1024*1024):raise ValueError('Unsupported image color profile')
        pixels=image.convert('RGB')
        pixels.info.clear()
        pixels.save(output,format='PNG',icc_profile=profile)
        if output.tell()>MAX_BYTES:raise ValueError('Canonical image exceeds limits')
        return output.getvalue(),image.size


def stage_images(directory:Path,owned_root:Path,attachments:list[dict]):
    """Server intake only, after repository owner checks. No client paths accepted.

    Unsupported reference images remain usable by their existing workflows;
    they simply do not become eligible comparison inputs. Ownership violations
    fail closed rather than being ignored.
    """
    root=owned_root.resolve();output=directory.resolve()/'inputs'
    if not output.resolve().is_relative_to(directory.resolve()):raise ValueError('Invalid input directory')
    rows=[]
    for item in attachments:
        if item.get('kind')!='image':continue
        aid=item.get('id','')
        if not re.fullmatch('[0-9a-f]{32}',aid):raise ValueError('Invalid owned attachment ID')
        source=Path(item.get('path','')).resolve()
        if source.parent!=root or source.stem!=aid or not source.is_file():raise ValueError('Comparison attachment is not owned by this conversation')
        if len(rows)>=8:continue
        if source.stat().st_size>MAX_BYTES:continue
        try:raw,size=canonical_image(source.read_bytes())
        except (ValueError,OSError):continue
        digest=hashlib.sha256(raw).hexdigest();name='compare-'+digest+'.png'
        output.mkdir(parents=True,exist_ok=True)
        target=output/name
        if not target.resolve().is_relative_to(output.resolve()):raise ValueError('Invalid canonical input path')
        target.write_bytes(raw)
        if not any(row['asset']=='assets/'+name for row in rows):
            rows.append({'attachment_id':aid,'asset':'assets/'+name,'sha256':digest,'width':size[0],'height':size[1]})
    return rows


def validate_assets(project:Path,spec:BeforeAfterNative):
    """Resolve only content-addressed files inside this render's asset folder."""
    root=project.resolve();paths=[];sizes=[];digests=[]
    for name in (spec.before_asset,spec.after_asset):
        if not re.fullmatch(ASSET,name):raise ValueError('Invalid comparison asset reference')
        path=(root/name).resolve()
        if not path.is_relative_to(root/'assets') or not path.is_file() or path.stat().st_size>MAX_BYTES:
            raise ValueError('Missing or unowned comparison image')
        raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if path.name!='compare-'+digest+'.png':raise ValueError('Comparison asset integrity failure')
        _,size=canonical_image(raw)
        paths.append(path);sizes.append(size);digests.append(digest)
    if sizes[0]!=sizes[1] or digests[0]==digests[1]:raise ValueError('Comparison needs two different supplied states with matching dimensions')
    return paths,digests


def restore_inputs(directory:Path,work:Path,rows:list[dict]):
    """Recreate version work assets from private immutable job inputs, on retry too."""
    root=directory.resolve();assets=work.resolve()/'assets';assets.mkdir(parents=True,exist_ok=True)
    if not assets.resolve().is_relative_to(work.resolve()):raise ValueError('Invalid work assets directory')
    for row in rows:
        name=row.get('asset','')
        if not re.fullmatch(ASSET,name):raise ValueError('Invalid saved comparison input')
        source=(root/'inputs'/Path(name).name).resolve();target=(assets/Path(name).name).resolve()
        if not source.is_relative_to(root/'inputs') or not target.is_relative_to(assets):raise ValueError('Saved image escapes owned job')
        if source.stat().st_size>MAX_BYTES or hashlib.sha256(source.read_bytes()).hexdigest()!=row.get('sha256'):
            raise ValueError('Saved comparison image changed')
        shutil.copy2(source,target)
