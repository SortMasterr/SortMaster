import asyncio
import unittest

from pydantic import ValidationError

from schemas.event import (
    BinType,
    CameraId,
    DetectedClass,
    EventCategory,
    EventCreate,
)
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


def createMisclassification(detectionId, detectedClass=DetectedClass.PLASTIC):
    return EventCreate(
        cameraId=CameraId.ELEVTOP,
        eventCategory=EventCategory.MISCLASSIFICATION,
        detectionId=detectionId,
        trackingId=7,
        detectedClass=detectedClass,
        binId="BIN-PAPER",
        binType=BinType.PAPER,
        isMisclassified=True,
        confidenceScore=0.91,
        modelVersion="yolo26-mvp-1",
    )


class EventMvpTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repository = MemoryEventRepository()
        self.service = EventService(self.repository)

    async def testDuplicateDetectionIdReturnsExistingEvent(self):
        eventCreate = createMisclassification("detection-001")

        firstEvent = await self.service.createEvent(eventCreate)
        secondEvent = await self.service.createEvent(eventCreate)

        self.assertEqual(firstEvent.eventId, secondEvent.eventId)
        self.assertEqual(1, len(self.repository.events))

    async def testCreationStatusMarksDuplicateAsNotNew(self):
        eventCreate = createMisclassification("detection-status")

        firstResult = await self.service.createEventWithStatus(
            eventCreate
        )
        secondResult = await self.service.createEventWithStatus(
            eventCreate
        )

        self.assertTrue(firstResult.created)
        self.assertFalse(secondResult.created)
        self.assertEqual(
            firstResult.event.eventId,
            secondResult.event.eventId,
        )

    async def testCooldownBlocksSameClassWithDifferentDetectionId(self):
        firstEvent = await self.service.createEvent(
            createMisclassification("detection-001")
        )
        secondEvent = await self.service.createEvent(
            createMisclassification("detection-002")
        )

        self.assertIsNotNone(firstEvent)
        self.assertIsNone(secondEvent)

    async def testConcurrentCooldownStoresOnlyOneEvent(self):
        results = await asyncio.gather(
            self.service.createEvent(
                createMisclassification("concurrent-001")
            ),
            self.service.createEvent(
                createMisclassification("concurrent-002")
            ),
        )

        self.assertEqual(
            1,
            sum(event is not None for event in results),
        )
        self.assertEqual(1, len(self.repository.events))

    async def testOverflowDoesNotUseTimeCooldown(self):
        def createOverflow(detectionId):
            return EventCreate(
                cameraId=CameraId.ELEVSIDE,
                eventCategory=EventCategory.OVERFLOW,
                detectionId=detectionId,
                binId="BIN-GENERAL",
                binType=BinType.GENERAL,
                overflowDuration=5.0,
                overflowThreshold=5.0,
                modelVersion="yolo26-mvp-1",
            )

        await self.service.createEvent(createOverflow("overflow-001"))
        await self.service.createEvent(createOverflow("overflow-002"))

        self.assertEqual(2, len(self.repository.events))

    async def testStatisticsSeparateOverflow(self):
        await self.service.createEvent(
            createMisclassification("detection-001")
        )
        await self.service.createEvent(
            EventCreate(
                cameraId=CameraId.ELEVSIDE,
                eventCategory=EventCategory.OVERFLOW,
                detectionId="overflow-001",
                binId="BIN-GENERAL",
                binType=BinType.GENERAL,
                overflowDuration=5.0,
                overflowThreshold=5.0,
                modelVersion="yolo26-mvp-1",
            )
        )

        statistics = await self.service.getStatistics()

        self.assertEqual(2, statistics.totalEventCount)
        self.assertEqual(1, statistics.misclassificationCount)
        self.assertEqual(1, statistics.overflowCount)

    def testCameraRoleValidation(self):
        with self.assertRaises(ValidationError):
            EventCreate(
                cameraId=CameraId.ELEVSIDE,
                eventCategory=EventCategory.MISCLASSIFICATION,
                detectionId="invalid-001",
                detectedClass=DetectedClass.PAPER,
                binId="BIN-PAPER",
                binType=BinType.PAPER,
                isMisclassified=True,
                confidenceScore=0.8,
                modelVersion="yolo26-mvp-1",
            )


if __name__ == "__main__":
    unittest.main()
