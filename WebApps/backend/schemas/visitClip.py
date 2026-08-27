from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from schemas.event import CameraId


class TrackStartedRequest(BaseModel):
    """GPU(tracking2.py)가 새 트랙을 발견하는 즉시 보내는 경량 신호(EP-14)."""

    trackId: int = Field(ge=0)
    cameraId: CameraId
    timestamp: datetime


class TrackEndedRequest(BaseModel):
    """GPU가 트랙을 확정 못 하고 놓쳤을 때 aiDisposal 대신 보내는 신호(EP-15)."""

    trackId: int = Field(ge=0)
    cameraId: CameraId
    timestamp: datetime
    result: Literal["unresolved"] = "unresolved"


class VisitClip(BaseModel):
    """presence 감지 기반 방문 녹화 — 판정 여부와 무관하게 항상 생성된다.

    설계 배경은 .agentfiles/architecture.md의 "재학습용 미확정 방문 캡처" 참고.
    """

    cameraId: CameraId
    startedAt: datetime
    endedAt: datetime
    imageFileId: str
    trackIds: list[int] = Field(default_factory=list)
    matchedEventIds: list[str] = Field(default_factory=list)
    unresolvedTrackIds: list[int] = Field(default_factory=list)


class VisitClipSummary(BaseModel):
    """관리자 웹의 방문 클립 목록/영상 열람용 응답 스키마(imageFileId는 노출하지 않고
    /media 하위 경로로만 접근하게 한다)."""

    id: str
    cameraId: CameraId
    startedAt: datetime
    endedAt: datetime
    trackIds: list[int]
    matchedEventIds: list[str]
    unresolvedTrackIds: list[int]
