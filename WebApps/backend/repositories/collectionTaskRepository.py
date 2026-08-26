import logging
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from repositories.mongoClient import getMongoDb
from schemas.collectionTask import (
    CollectionTask,
    CollectionTaskStatus,
)
from schemas.event import BinType, CameraId


logger = logging.getLogger(__name__)


class CollectionTaskRepository:
    def __init__(self):
        self.indexesReady = False

    @property
    def collection(self):
        return getMongoDb()["collectionTasks"]

    async def ensureIndexes(self) -> None:
        if self.indexesReady:
            return
        await self.collection.create_index(
            "collectionTaskId",
            unique=True,
            name="uq_collectionTasks_collectionTaskId",
        )
        await self.collection.create_index(
            "activeBinId",
            unique=True,
            sparse=True,
            name="uq_collectionTasks_activeBinId",
        )
        await self.collection.create_index(
            [("taskStatus", ASCENDING), ("createdAt", ASCENDING)],
            name="ix_collectionTasks_status_createdAt",
        )
        self.indexesReady = True

    def _toDocument(self, task: CollectionTask) -> dict:
        document = task.model_dump()
        document["binType"] = task.binType.value
        document["cameraId"] = task.cameraId.value
        document["taskStatus"] = task.taskStatus.value
        if task.taskStatus in {
            CollectionTaskStatus.OPEN,
            CollectionTaskStatus.ACKNOWLEDGED,
        }:
            document["activeBinId"] = task.binId
        return document

    def _fromDocument(self, document: dict) -> CollectionTask:
        return CollectionTask(
            collectionTaskId=document["collectionTaskId"],
            binId=document["binId"],
            binType=BinType(document["binType"]),
            cameraId=CameraId(document["cameraId"]),
            relatedEventId=document["relatedEventId"],
            taskStatus=CollectionTaskStatus(document["taskStatus"]),
            detectedAt=self._normalizeDateTime(document["detectedAt"]),
            createdAt=self._normalizeDateTime(document["createdAt"]),
            acknowledgedAt=self._optionalDateTime(document.get("acknowledgedAt")),
            completedAt=self._optionalDateTime(document.get("completedAt")),
            processingSeconds=document.get("processingSeconds"),
            escalationLevel=document.get("escalationLevel", 0),
            initialNotificationAt=self._optionalDateTime(document.get("initialNotificationAt")),
            reminderNotificationAt=self._optionalDateTime(document.get("reminderNotificationAt")),
            escalationNotificationAt=self._optionalDateTime(document.get("escalationNotificationAt")),
            lastNotificationAt=self._optionalDateTime(document.get("lastNotificationAt")),
            notificationAttemptCount=document.get("notificationAttemptCount", 0),
            nextNotificationAttemptAt=self._optionalDateTime(document.get("nextNotificationAttemptAt")),
            lastFailureReason=document.get("lastFailureReason"),
        )

    async def create(self, task: CollectionTask) -> tuple[CollectionTask, bool]:
        await self.ensureIndexes()
        try:
            await self.collection.insert_one(self._toDocument(task))
            return task, True
        except DuplicateKeyError:
            existing = await self.findActiveByBinId(task.binId)
            if existing is None:
                raise
            return existing, False

    async def findById(self, collectionTaskId: str) -> CollectionTask | None:
        document = await self.collection.find_one(
            {"collectionTaskId": collectionTaskId}
        )
        return self._fromDocument(document) if document else None

    async def findActiveByBinId(self, binId: str) -> CollectionTask | None:
        document = await self.collection.find_one({"activeBinId": binId})
        return self._fromDocument(document) if document else None

    async def findAll(
        self,
        taskStatus: CollectionTaskStatus | None = None,
        limit: int = 50,
    ) -> tuple[list[CollectionTask], int]:
        query = {"taskStatus": taskStatus.value} if taskStatus else {}
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("createdAt", DESCENDING).limit(limit)
        return [self._fromDocument(item) async for item in cursor], total

    async def findActionable(self, now: datetime, limit: int = 50) -> list[CollectionTask]:
        query = {
            "taskStatus": {"$in": ["OPEN", "ACKNOWLEDGED"]},
            "$or": [
                {"nextNotificationAttemptAt": None},
                {"nextNotificationAttemptAt": {"$exists": False}},
                {"nextNotificationAttemptAt": {"$lte": now}},
            ],
        }
        cursor = self.collection.find(query).sort("createdAt", ASCENDING).limit(limit)
        return [self._fromDocument(item) async for item in cursor]

    async def updateFields(self, collectionTaskId: str, fields: dict) -> CollectionTask | None:
        setFields = dict(fields)
        unsetFields = {}
        if fields.get("taskStatus") in {
            CollectionTaskStatus.COMPLETED,
            CollectionTaskStatus.CANCELLED,
        }:
            unsetFields["activeBinId"] = ""
        if isinstance(setFields.get("taskStatus"), CollectionTaskStatus):
            setFields["taskStatus"] = setFields["taskStatus"].value
        update = {"$set": setFields}
        if unsetFields:
            update["$unset"] = unsetFields
        document = await self.collection.find_one_and_update(
            {"collectionTaskId": collectionTaskId},
            update,
            return_document=ReturnDocument.AFTER,
        )
        return self._fromDocument(document) if document else None

    async def getMetrics(self, todayStart: datetime) -> dict:
        openCount = await self.collection.count_documents({"taskStatus": "OPEN"})
        acknowledgedCount = await self.collection.count_documents({"taskStatus": "ACKNOWLEDGED"})
        escalatedCount = await self.collection.count_documents({
            "taskStatus": {"$in": ["OPEN", "ACKNOWLEDGED"]},
            "escalationLevel": 2,
        })
        completedTodayCount = await self.collection.count_documents({
            "taskStatus": "COMPLETED",
            "completedAt": {"$gte": todayStart},
        })
        pipeline = [
            {"$match": {"taskStatus": "COMPLETED", "processingSeconds": {"$ne": None}}},
            {"$group": {"_id": None, "average": {"$avg": "$processingSeconds"}}},
        ]
        averageRows = [row async for row in self.collection.aggregate(pipeline)]
        return {
            "openTaskCount": openCount,
            "acknowledgedTaskCount": acknowledgedCount,
            "escalatedTaskCount": escalatedCount,
            "completedTodayCount": completedTodayCount,
            "averageProcessingSeconds": averageRows[0]["average"] if averageRows else None,
        }

    @staticmethod
    def _normalizeDateTime(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    def _optionalDateTime(self, value: datetime | None) -> datetime | None:
        return self._normalizeDateTime(value) if value else None


collectionTaskRepository = CollectionTaskRepository()
