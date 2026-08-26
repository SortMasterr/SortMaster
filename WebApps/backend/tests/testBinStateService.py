import unittest

from schemas.binState import BinCurrentState, BinStateUpdate
from schemas.event import BinType, CameraId, DetectedClass, EventCategory
from services.binStateService import BinStateService
from services.eventService import EventService


class MemoryEventRepository:
    def __init__(self):
        self.events = []

    async def findByDetectionId(self, detectionId):
        return next(
            (
                event
                for event in self.events
                if event.detectionId == detectionId
            ),
            None,
        )

    async def save(self, event):
        self.events.append(event)
        return event

    async def findAll(self, fromDate=None, toDate=None):
        return list(reversed(self.events))

    async def findById(self, eventId):
        return next(
            (
                event
                for event in self.events
                if event.eventId == eventId
            ),
            None,
        )

    async def countByDetectedClass(self, fromDate=None, toDate=None):
        return {
            detectedClass: sum(
                event.detectedClass == detectedClass
                for event in self.events
            )
            for detectedClass in DetectedClass
        }

    async def countByEventCategory(self, fromDate=None, toDate=None):
        return {
            eventCategory: sum(
                event.eventCategory == eventCategory
                for event in self.events
            )
            for eventCategory in EventCategory
        }

    async def getStatisticsCounts(self, fromDate=None, toDate=None):
        return (
            await self.countByDetectedClass(fromDate, toDate),
            await self.countByEventCategory(fromDate, toDate),
        )


class MemoryBinStateRepository:
    def __init__(self):
        self.binStatesByBinId = {}

    async def findById(self, binId):
        return self.binStatesByBinId.get(binId)

    async def findAll(self):
        return list(self.binStatesByBinId.values())

    async def upsert(self, binState):
        self.binStatesByBinId[binState.binId] = binState
        return binState


class MemoryCollectionTaskService:
    def __init__(self):
        self.events = []

    async def createForOverflow(self, event):
        self.events.append(event)


def createUpdate(
    binId="BIN-GENERAL",
    detectionId="detection-001",
    currentState=BinCurrentState.FULL,
    sessionId="session-1",
):
    return BinStateUpdate(
        binId=binId,
        binType=BinType.NORMAL,
        sessionId=sessionId,
        currentState=currentState,
        confidenceScore=0.95,
        overflowDuration=6.0,
        overflowThreshold=5.0,
        detectionId=detectionId,
        modelVersion="overflow-mvp-1",
    )


class BinStateServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.eventRepository = MemoryEventRepository()
        self.eventService = EventService(self.eventRepository)
        self.binStateRepository = MemoryBinStateRepository()
        self.service = BinStateService(
            self.binStateRepository,
            self.eventService,
        )

    async def testNormalToFullCreatesOverflowEvent(self):
        binState, eventResult = await self.service.applyUpdate(
            createUpdate()
        )

        self.assertEqual(BinCurrentState.FULL, binState.currentState)
        self.assertIsNotNone(eventResult)
        self.assertTrue(eventResult.created)
        self.assertEqual(1, len(self.eventRepository.events))
        self.assertEqual(
            eventResult.event.eventId,
            binState.activeOverflowEventId,
        )

    async def testStayingFullDoesNotCreateAnotherEvent(self):
        await self.service.applyUpdate(createUpdate())
        binState, eventResult = await self.service.applyUpdate(
            createUpdate(detectionId="detection-002")
        )

        self.assertIsNone(eventResult)
        self.assertEqual(1, len(self.eventRepository.events))
        self.assertEqual(
            BinCurrentState.FULL, binState.currentState
        )

    async def testFullToNormalDoesNotCreateEventAndResetsActiveId(self):
        await self.service.applyUpdate(createUpdate())
        binState, eventResult = await self.service.applyUpdate(
            createUpdate(
                detectionId="detection-002",
                currentState=BinCurrentState.NORMAL,
            )
        )

        self.assertIsNone(eventResult)
        self.assertEqual(1, len(self.eventRepository.events))
        self.assertEqual(
            BinCurrentState.NORMAL, binState.currentState
        )
        self.assertIsNone(binState.activeOverflowEventId)

    async def testNormalToFullAgainAfterRecoveryCreatesNewEvent(self):
        await self.service.applyUpdate(createUpdate())
        await self.service.applyUpdate(
            createUpdate(
                detectionId="detection-002",
                currentState=BinCurrentState.NORMAL,
            )
        )
        binState, eventResult = await self.service.applyUpdate(
            createUpdate(detectionId="detection-003")
        )

        self.assertIsNotNone(eventResult)
        self.assertTrue(eventResult.created)
        self.assertEqual(2, len(self.eventRepository.events))
        self.assertEqual(
            eventResult.event.eventId,
            binState.activeOverflowEventId,
        )

    async def testCameraRoleValidation(self):
        with self.assertRaises(ValueError):
            BinStateUpdate(
                binId="BIN-GENERAL",
                cameraId=CameraId.ELEVTOP,
                binType=BinType.NORMAL,
                sessionId="session-1",
                currentState=BinCurrentState.FULL,
                confidenceScore=0.9,
                overflowDuration=1.0,
                detectionId="detection-invalid",
                modelVersion="overflow-mvp-1",
            )

    async def testFullTransitionRequestsCollectionTaskCreation(self):
        collectionTasks = MemoryCollectionTaskService()
        service = BinStateService(
            self.binStateRepository,
            self.eventService,
            collectionTasks,
        )
        await service.applyUpdate(createUpdate())
        self.assertEqual(1, len(collectionTasks.events))
        self.assertEqual(EventCategory.OVERFLOW, collectionTasks.events[0].eventCategory)


if __name__ == "__main__":
    unittest.main()
