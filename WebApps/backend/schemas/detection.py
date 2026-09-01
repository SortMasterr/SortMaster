from pydantic import BaseModel, Field, model_validator

from schemas.event import (
    BinType,
    CameraId,
    DetectedClass,
    EventCategory,
)


class DetectionStart(BaseModel):
    cameraId: CameraId


class DetectionStartResponse(BaseModel):
    recordingId: str


class DetectionStop(BaseModel):
    recordingId: str
    cameraId: CameraId
    eventCategory: EventCategory = EventCategory.MISCLASSIFICATION
    detectionId: str = Field(min_length=1)
    trackingId: int | None = Field(default=None, ge=0)
    detectedClass: DetectedClass | None = None
    binId: str = Field(min_length=1)
    binType: BinType
    isMisclassified: bool | None = None
    confidenceScore: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    overflowDuration: float | None = Field(default=None, ge=0.0)
    overflowThreshold: float | None = Field(default=None, ge=0.0)
    modelVersion: str = Field(min_length=1)

    @model_validator(mode="after")
    def checkCategoryFields(self):
        if self.eventCategory == EventCategory.MISCLASSIFICATION:
            if self.cameraId != CameraId.ELEVTOP:
                raise ValueError(
                    "misclassification 종료 신호는 ELEV-TOP 카메라만 사용할 수 있습니다."
                )

            if (
                self.detectedClass is None
                or self.isMisclassified is None
                or self.confidenceScore is None
            ):
                raise ValueError(
                    "misclassification 종료 신호에는 detectedClass/"
                    "isMisclassified/confidenceScore가 모두 필요합니다."
                )

        if self.eventCategory == EventCategory.OVERFLOW:
            if self.cameraId != CameraId.ELEVSIDE:
                raise ValueError(
                    "overflow 종료 신호는 ELEV-SIDE 카메라만 사용할 수 있습니다."
                )

            if (
                self.detectedClass is not None
                or self.isMisclassified is not None
                or self.confidenceScore is not None
            ):
                raise ValueError(
                    "overflow 종료 신호에는 분류 결과 필드를 사용할 수 없습니다."
                )

        return self
