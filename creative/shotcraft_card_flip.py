"""Explicit content for the pinned three-card reveal; no demo claims/defaults.

An evidence reference is required, but is not proof of factual accuracy or
authorization to publish. Actual shaped text is checked during native rendering.
"""
from typing import Literal
import math
from pydantic import BaseModel, ConfigDict, Field, field_validator


def plain(value,limit):
    if not value.strip() or len(value.encode("utf-16-le",errors="surrogatepass"))//2>limit or any(c in value for c in "<>\n\r"):
        raise ValueError("Use bounded single-line plain text")
    return value.strip()


class FlipCardContent(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name:str=Field(min_length=1,max_length=20)
    description:str=Field(min_length=1,max_length=48)
    front_lines:tuple[str,...]=Field(min_length=3,max_length=3)
    before:float=Field(ge=0,le=999.99,allow_inf_nan=False)
    after:float=Field(ge=0,le=999.99,allow_inf_nan=False)
    unit:str=Field(min_length=1,max_length=8)
    result_label:str=Field(min_length=1,max_length=32)
    evidence:str=Field(min_length=1,max_length=160)

    @field_validator("name","description","unit","result_label","evidence")
    @classmethod
    def bounded_text(cls,value,info):
        return plain(value,{"name":20,"description":48,"unit":8,"result_label":32,"evidence":160}[info.field_name])

    @field_validator("front_lines")
    @classmethod
    def lines(cls,values):
        return tuple(plain(v,24) for v in values)


class CardFlipNative(BaseModel):
    model_config=ConfigDict(extra="forbid")
    resource_id:Literal["shotcraft:card-flip-reveal"]
    caption:str=Field(min_length=1,max_length=48)
    kicker:str=Field(min_length=1,max_length=24)
    front_label:str=Field(min_length=1,max_length=12)
    before_label:str=Field(min_length=1,max_length=12)
    after_label:str=Field(min_length=1,max_length=12)
    cards:tuple[FlipCardContent,...]=Field(min_length=3,max_length=3)
    locale:Literal["fa-IR","en-US"]="fa-IR"

    @field_validator("caption","kicker","front_label","before_label","after_label")
    @classmethod
    def bounded_text(cls,value,info):
        return plain(value,{"caption":48,"kicker":24,"front_label":12,"before_label":12,"after_label":12}[info.field_name])


def reading_frames(spec):
    front=max(60,*(math.ceil(len(' '.join([c.name,c.description,*c.front_lines]).split())/2.5*30) for c in spec.cards))
    back=max(40,*(math.ceil(len(' '.join([c.name,c.result_label,spec.before_label,spec.after_label,c.unit]).split())/2.5*30) for c in spec.cards))
    return front+50+back
