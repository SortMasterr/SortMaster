"""GPU 서버 추론 스크립트(`tracking2.py`/`sideOverflow.py`)의 생존 여부 판정.

판정 이벤트(`aiDisposal`/`binStates`)와 별개로 GPU가 보내는 하트비트의 마지막 수신
시각을 저장해두고, 조회 시점마다 임계값을 넘었는지 계산해 ONLINE/OFFLINE을 반환한다
(설계는 `Docs/ARCHITECTURE.md`의 "추론 인프라" > "GPU 하트비트(헬스체크)" 참고).
"""
from datetime import datetime, timezone

from repositories.gpuHeartbeatRepository import (
    GpuHeartbeatRepository,
    gpuHeartbeatRepository,
)
from schemas.event import CameraId
from schemas.gpuHeartbeat import CameraStatus, GpuHeartbeatStatus


# GPU 서버가 30초~1분 주기로 하트비트를 보내는 걸 전제(architecture.md). 재시도/지연을
# 감안해 그 3배인 90초 안에 신호가 없으면 OFFLINE으로 표시 — 실측 후 조정 필요한
# TBD 성격의 값(README의 confidence threshold와 동일한 성격).
OFFLINE_THRESHOLD_SECONDS = 90.0

# 실시간 경로에서 GPU 추론을 실제로 담당하는 카메라만 상태를 표시한다(architecture.md
# "역할 분담" 참고) — REST-4F-01은 미설치라 대상 아님.
MONITORED_CAMERA_IDS = [CameraId.ELEVTOP, CameraId.ELEVSIDE]


class GpuHeartbeatService:
    def __init__(self, repository: GpuHeartbeatRepository):
        self.repository = repository

    async def recordHeartbeat(self, cameraId: CameraId) -> GpuHeartbeatStatus:
        now = datetime.now(timezone.utc)
        await self.repository.recordSeen(cameraId, now)

        return GpuHeartbeatStatus(
            cameraId=cameraId,
            status=CameraStatus.ONLINE,
            lastSeenAt=now,
        )

    async def getStatuses(self) -> list[GpuHeartbeatStatus]:
        lastSeenByCameraId = await self.repository.findLastSeenByCameraId()
        now = datetime.now(timezone.utc)

        return [
            self._toStatus(cameraId, lastSeenByCameraId.get(cameraId.value), now)
            for cameraId in MONITORED_CAMERA_IDS
        ]

    def _toStatus(
        self,
        cameraId: CameraId,
        lastSeenAt: datetime | None,
        now: datetime,
    ) -> GpuHeartbeatStatus:
        isOnline = (
            lastSeenAt is not None
            and (now - lastSeenAt).total_seconds() <= OFFLINE_THRESHOLD_SECONDS
        )

        return GpuHeartbeatStatus(
            cameraId=cameraId,
            status=CameraStatus.ONLINE if isOnline else CameraStatus.OFFLINE,
            lastSeenAt=lastSeenAt,
        )


gpuHeartbeatService = GpuHeartbeatService(gpuHeartbeatRepository)
