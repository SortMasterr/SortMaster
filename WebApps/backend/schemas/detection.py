from pydantic import BaseModel, Field

from schemas.event import CameraId, DetectedClass


class DetectionStart(BaseModel):
    cameraId: CameraId


class DetectionStartResponse(BaseModel):
    recordingId: str


class DetectionStop(BaseModel):
    recordingId: str
    cameraId: CameraId
    detectedClass: DetectedClass
    isMisclassified: bool
    confidenceScore: float = Field(ge=0.0, le=1.0)
