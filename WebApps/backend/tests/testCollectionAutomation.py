import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from schemas.collectionTask import (
    CollectionAutomationActionType,
    CollectionTask,
    CollectionTaskStatus,
)
from schemas.event import (
    ActionTaken,
    BinType,
    CameraId,
    Event,
    EventCategory,
)
from services.collectionAutomationConfig import CollectionAutomationConfig
from services.collectionTaskService import CollectionTaskService


class MemoryCollectionTaskRepository:
    def __init__(self):
        self.tasks = {}

    async def create(self, task):
        existing = next(
            (
                item for item in self.tasks.values()
                if item.binId == task.binId
                and item.taskStatus in {CollectionTaskStatus.OPEN, CollectionTaskStatus.ACKNOWLEDGED}
            ),
            None,
        )
        if existing:
            return existing, False
        self.tasks[task.collectionTaskId] = task
        return task, True

    async def findById(self, collectionTaskId):
        return self.tasks.get(collectionTaskId)

    async def updateFields(self, collectionTaskId, fields):
        task = self.tasks.get(collectionTaskId)
        if task is None:
            return None
        values = task.model_dump()
        values.update(fields)
        updated = CollectionTask(**values)
        self.tasks[collectionTaskId] = updated
        return updated


class MemoryAutomationRepository:
    def __init__(self):
        self.runs = []

    async def recordRun(self, *arguments):
        self.runs.append(arguments)


def overflowEvent(eventId="event-1"):
    return Event(
        eventId=eventId,
        timestamp=datetime.now(timezone.utc),
        cameraId=CameraId.ELEVSIDE,
        eventCategory=EventCategory.OVERFLOW,
        detectionId=f"detection-{eventId}",
        binId="BIN-RECYCLABLES",
        binType=BinType.RECYCLABLES,
        overflowDuration=6.0,
        overflowThreshold=5.0,
        modelVersion="overflow-test-1",
        actionTaken=ActionTaken.LIGHT_AND_SOUND,
    )


class CollectionTaskServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repository = MemoryCollectionTaskRepository()
        self.service = CollectionTaskService(
            self.repository,
            MemoryAutomationRepository(),
        )

    async def testFullEventCreatesOnlyOneActiveTaskPerBin(self):
        with patch.dict("os.environ", {"RPA_COLLECTION_ENABLED": "true"}):
            first, firstCreated = await self.service.createForOverflow(overflowEvent())
            second, secondCreated = await self.service.createForOverflow(overflowEvent("event-2"))

        self.assertTrue(firstCreated)
        self.assertFalse(secondCreated)
        self.assertEqual(first.collectionTaskId, second.collectionTaskId)

    async def testDisabledAutomationDoesNotCreateTask(self):
        with patch.dict("os.environ", {"RPA_COLLECTION_ENABLED": "false"}):
            result = await self.service.createForOverflow(overflowEvent())
        self.assertIsNone(result)

    async def testCompleteRecordsProcessingTime(self):
        with patch.dict("os.environ", {"RPA_COLLECTION_ENABLED": "true"}):
            task, _ = await self.service.createForOverflow(overflowEvent())
        completed = await self.service.complete(task.collectionTaskId)
        self.assertEqual(CollectionTaskStatus.COMPLETED, completed.taskStatus)
        self.assertIsNotNone(completed.completedAt)
        self.assertGreaterEqual(completed.processingSeconds, 0)


class CollectionNotificationSelectionTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.config = CollectionAutomationConfig(
            enabled=True,
            assigneeEmail="worker@example.com",
            managerEmail="manager@example.com",
            reminderMinutes=10,
            escalationMinutes=20,
            pollSeconds=30,
            retrySeconds=60,
        )

    def task(self, **changes):
        values = CollectionTask(
            collectionTaskId="task-1",
            binId="BIN-NORMAL",
            binType=BinType.NORMAL,
            cameraId=CameraId.ELEVSIDE,
            relatedEventId="event-1",
            taskStatus=CollectionTaskStatus.OPEN,
            detectedAt=self.now - timedelta(minutes=30),
            createdAt=self.now - timedelta(minutes=30),
        ).model_dump()
        values.update(changes)
        return CollectionTask(**values)

    def testNotificationsRemainOrderedAfterLongDowntime(self):
        from RPAs.collectionAutomation.collectionScheduler import selectNotification

        initial = selectNotification(self.task(), self.now, self.config)
        reminder = selectNotification(
            self.task(initialNotificationAt=self.now - timedelta(minutes=29)),
            self.now,
            self.config,
        )
        escalation = selectNotification(
            self.task(
                initialNotificationAt=self.now - timedelta(minutes=29),
                reminderNotificationAt=self.now - timedelta(minutes=15),
            ),
            self.now,
            self.config,
        )
        self.assertEqual(CollectionAutomationActionType.INITIAL, initial[0])
        self.assertEqual(CollectionAutomationActionType.REMINDER, reminder[0])
        self.assertEqual(CollectionAutomationActionType.ESCALATION, escalation[0])


if __name__ == "__main__":
    unittest.main()
