from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.event import BinType, CameraId, normalizeBinId


class BinCurrentState(str, Enum):
    NORMAL = "NORMAL"
    FULL = "FULL"


class BinStateUpdate(BaseModel):
    """GPU 서버 `inference`(ELEV-SIDE 넘침 감지)가 보내는 통 상태 갱신 신호.

    `currentState`가 이전 저장값과 다를 때만 상태 전환으로 처리된다(binStateService).
    NORMAL→FULL 전환 시에만 `detectionId`/`modelVersion`/`overflowThreshold`가
    실제로 EVENT(overflow) 생성에 사용된다 — 매 프레임 보내는 게 아니라 감지 루프가
    적당한 주기로 호출하는 걸 전제로, 값 자체는 매번 요구한다(전환 시점에만 갑자기
    필드가 없어서 실패하는 상황 방지).
    """

    binId: str = Field(min_length=1)
    cameraId: CameraId = CameraId.ELEVSIDE
    binType: BinType
    sessionId: str = Field(min_length=1)
    currentState: BinCurrentState
    confidenceScore: float = Field(ge=0.0, le=1.0)
    overflowDuration: float = Field(ge=0.0)
    overflowThreshold: float | None = Field(default=None, ge=0.0)
    detectionId: str = Field(min_length=1)
    modelVersion: str = Field(min_length=1)

    @field_validator("binId", mode="before")
    @classmethod
    def normalizeLegacyBinId(cls, value):
        return normalizeBinId(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def checkCameraRole(self):
        if self.cameraId != CameraId.ELEVSIDE:
            raise ValueError(
                "BIN_STATES 갱신은 ELEV-SIDE 카메라에서만 가능합니다."
            )

        return self


class BinState(BaseModel):
    binId: str
    cameraId: CameraId
    binType: BinType
    sessionId: str
    currentState: BinCurrentState
    confidenceScore: float
    overflowDuration: float
    lastChangedAt: datetime
    activeOverflowEventId: str | None = None

    @field_validator("binId", mode="before")
    @classmethod
    def normalizeLegacyBinId(cls, value):
        return normalizeBinId(value) if isinstance(value, str) else value
