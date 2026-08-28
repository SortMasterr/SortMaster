from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from schemas.event import CameraId


class CameraStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class GpuHeartbeatPing(BaseModel):
    """GPU 서버의 `tracking2.py`(ELEV-TOP)/`sideOverflow.py`(ELEV-SIDE)가 판정 이벤트와
    무관하게 일정 주기(30초~1분)로 보내는 생존 신호. 설계는 `Docs/ARCHITECTURE.md`의
    "추론 인프라" > "GPU 하트비트(헬스체크)" 참고.
    """

    cameraId: CameraId


class GpuHeartbeatStatus(BaseModel):
    cameraId: CameraId
    status: CameraStatus
    lastSeenAt: datetime | None = None
