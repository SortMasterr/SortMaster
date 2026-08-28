import unittest
from datetime import datetime, timedelta, timezone

from schemas.event import CameraId
from schemas.gpuHeartbeat import CameraStatus
from services.gpuHeartbeatService import (
    OFFLINE_THRESHOLD_SECONDS,
    GpuHeartbeatService,
)


class MemoryGpuHeartbeatRepository:
    def __init__(self):
        self.lastSeenByCameraId = {}

    async def recordSeen(self, cameraId, seenAt):
        self.lastSeenByCameraId[cameraId.value] = seenAt

    async def findLastSeenByCameraId(self):
        return dict(self.lastSeenByCameraId)


class GpuHeartbeatServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repository = MemoryGpuHeartbeatRepository()
        self.service = GpuHeartbeatService(self.repository)

    async def testRecordHeartbeatReturnsOnlineWithLastSeenAt(self):
        status = await self.service.recordHeartbeat(CameraId.ELEVTOP)

        self.assertEqual(CameraId.ELEVTOP, status.cameraId)
        self.assertEqual(CameraStatus.ONLINE, status.status)
        self.assertIsNotNone(status.lastSeenAt)

    async def testNeverSeenCameraIsOffline(self):
        statuses = await self.service.getStatuses()
        byCameraId = {status.cameraId: status for status in statuses}

        self.assertEqual(
            CameraStatus.OFFLINE, byCameraId[CameraId.ELEVTOP].status
        )
        self.assertIsNone(byCameraId[CameraId.ELEVTOP].lastSeenAt)

    async def testRecentHeartbeatIsOnline(self):
        await self.service.recordHeartbeat(CameraId.ELEVTOP)

        statuses = await self.service.getStatuses()
        byCameraId = {status.cameraId: status for status in statuses}

        self.assertEqual(
            CameraStatus.ONLINE, byCameraId[CameraId.ELEVTOP].status
        )

    async def testStaleHeartbeatIsOffline(self):
        staleTime = datetime.now(timezone.utc) - timedelta(
            seconds=OFFLINE_THRESHOLD_SECONDS + 1
        )
        await self.repository.recordSeen(CameraId.ELEVSIDE, staleTime)

        statuses = await self.service.getStatuses()
        byCameraId = {status.cameraId: status for status in statuses}

        self.assertEqual(
            CameraStatus.OFFLINE, byCameraId[CameraId.ELEVSIDE].status
        )
        self.assertEqual(staleTime, byCameraId[CameraId.ELEVSIDE].lastSeenAt)

    async def testGetStatusesCoversBothMonitoredCameras(self):
        await self.service.recordHeartbeat(CameraId.ELEVTOP)

        statuses = await self.service.getStatuses()
        cameraIds = {status.cameraId for status in statuses}

        self.assertEqual({CameraId.ELEVTOP, CameraId.ELEVSIDE}, cameraIds)


if __name__ == "__main__":
    unittest.main()
