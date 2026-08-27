"""GPU_HEARTBEATS 저장소 — `cameraId`당 마지막 수신 시각 1행만 유지하는 upsert 컬렉션.

ONLINE/OFFLINE 판정은 저장하지 않는다(임계값이 바뀌어도 재계산만 하면 되도록,
`gpuHeartbeatService`가 조회 시점에 `lastSeenAt`으로부터 매번 계산한다).
"""
import logging
from datetime import datetime, timezone

from repositories.mongoClient import getMongoDb
from schemas.event import CameraId


logger = logging.getLogger(__name__)


class GpuHeartbeatRepository:
    def __init__(self):
        self.indexesReady = False

    @property
    def collection(self):
        return getMongoDb()["gpuHeartbeats"]

    async def ensureIndexes(self) -> None:
        if self.indexesReady:
            return

        await self.collection.create_index(
            "cameraId",
            unique=True,
            name="uq_gpuHeartbeats_cameraId",
        )
        self.indexesReady = True

    async def recordSeen(
        self,
        cameraId: CameraId,
        seenAt: datetime,
    ) -> None:
        await self.ensureIndexes()

        await self.collection.update_one(
            {"cameraId": cameraId.value},
            {"$set": {"cameraId": cameraId.value, "lastSeenAt": seenAt}},
            upsert=True,
        )

    async def findLastSeenByCameraId(self) -> dict[str, datetime]:
        cursor = self.collection.find({})
        lastSeenByCameraId: dict[str, datetime] = {}

        async for document in cursor:
            try:
                cameraId = document["cameraId"]
                lastSeenAt = self.normalizeDateTime(document["lastSeenAt"])
            except (KeyError, TypeError) as error:
                logger.warning(
                    "Skipping incompatible gpuHeartbeat document %r: %s",
                    document.get("_id"),
                    error,
                )
                continue

            lastSeenByCameraId[cameraId] = lastSeenAt

        return lastSeenByCameraId

    def normalizeDateTime(self, dateTime: datetime) -> datetime:
        if dateTime.tzinfo is None:
            return dateTime.replace(tzinfo=timezone.utc)

        return dateTime


gpuHeartbeatRepository = GpuHeartbeatRepository()
