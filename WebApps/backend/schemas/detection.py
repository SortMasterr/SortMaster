from pydantic import BaseModel, Field

from schemas.event import BinType, CameraId, DetectedClass


class DetectionStart(BaseModel):
    cameraId: CameraId


class DetectionStartResponse(BaseModel):
    recordingId: str


class DetectionStop(BaseModel):
    recordingId: str
    cameraId: CameraId
    detectionId: str = Field(min_length=1)
    trackingId: int | None = Field(default=None, ge=0)
    detectedClass: DetectedClass
    binId: str = Field(min_length=1)
    binType: BinType
    isMisclassified: bool
    confidenceScore: float = Field(ge=0.0, le=1.0)
    modelVersion: str = Field(min_length=1)
