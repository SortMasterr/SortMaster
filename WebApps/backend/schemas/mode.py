from enum import Enum

from pydantic import BaseModel


class Mode(str, Enum):
    manage = "MANAGE"
    collect = "COLLECT"


class ModeUpdate(BaseModel):
    mode: Mode


class ModeResponse(BaseModel):
    mode: Mode