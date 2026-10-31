"""A bounded nine-image collection, not the upstream fictional dashboard covers."""
import math
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator
from .shotcraft_card_flip import plain
from .shotcraft_compare import ASSET,validate_image_references


class StackCard(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title:str=Field(min_length=1,max_length=12)
    meta:str=Field(min_length=1,max_length=16)
    asset:str=Field(pattern=ASSET)

    @field_validator('title','meta')
    @classmethod
    def copy(cls,value,info):return plain(value,12 if info.field_name=='title' else 16)


class CardStackNative(BaseModel):
    model_config=ConfigDict(extra='forbid')
    resource_id:Literal['shotcraft:card-stack']
    caption:str=Field(min_length=1,max_length=48)
    kicker:str=Field(min_length=1,max_length=24)
    subtitle:str=Field(min_length=1,max_length=64)
    cards:tuple[StackCard,...]=Field(min_length=9,max_length=9)
    locale:Literal['fa-IR','en-US']='fa-IR'

    @field_validator('caption','kicker','subtitle')
    @classmethod
    def copy(cls,value,info):return plain(value,{'caption':48,'kicker':24,'subtitle':64}[info.field_name])

    @model_validator(mode='after')
    def unique_images(self):
        if len({c.asset for c in self.cards})!=9:raise ValueError('Supply nine distinct collection images')
        return self


def required_seconds(spec):
    # Original reveal completes after frame 130; preserve a readable final hold.
    words=max(len(spec.caption.split()),len(spec.subtitle.split()))
    return max(6,(130+max(45,math.ceil(words/2.5*30)))/30)


def validate_assets(project,spec):
    paths,digests,_=validate_image_references(project,[card.asset for card in spec.cards])
    return paths,digests
