from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class CameraId(str, Enum):
    ELEV01 = "ELEV-01"
    ELEV02 = "ELEV-02"
    REST4F01 = "REST-4F-01"


class DetectedClass(str, Enum):
    GENERAL = "general"
    PAPER = "paper"
    PLASTIC = "plastic"
    COFFEE_CUP = "coffeeCup"
    MIXED = "mixed"
    UNCERTAIN = "uncertain"


class ActionTaken(str, Enum):
    LIGHT_AND_SOUND = "lightAndSound"
    SOUND_ONLY = "soundOnly"
    LIGHT_ONLY = "lightOnly"
    NOTIFICATION_ONLY = "notificationOnly"
    NONE = "none"


class EventCreate(BaseModel):
    cameraId: CameraId
    detectedClass: DetectedClass
    isMisclassified: bool
    confidenceScore: float = Field(
        ge=0.0,
        le=1.0,
    )


class Event(EventCreate):
    eventId: str
    timestamp: datetime
    actionTaken: ActionTaken
    imageFileId: str | None = None
    notes: str | None = None