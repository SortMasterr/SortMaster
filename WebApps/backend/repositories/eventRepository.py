from datetime import datetime, timezone

from repositories.mongoClient import getMongoDb
from schemas.event import (
    ActionTaken,
    CameraId,
    DetectedClass,
    Event,
    EventCategory,
)


class EventRepository:
    @property
    def collection(self):
        return getMongoDb()["events"]

    def _toDocument(self, event: Event) -> dict:
        document = event.model_dump()
        document["cameraId"] = event.cameraId.value
        document["eventCategory"] = event.eventCategory.value
        document["detectedClass"] = (
            event.detectedClass.value
            if event.detectedClass is not None
            else None
        )
        document["actionTaken"] = event.actionTaken.value

        return document

    def _fromDocument(self, document: dict) -> Event:
        return Event(
            eventId=document["eventId"],
            timestamp=document["timestamp"],
            cameraId=CameraId(document["cameraId"]),
            eventCategory=EventCategory(document["eventCategory"]),
            detectedClass=(
                DetectedClass(document["detectedClass"])
                if document.get("detectedClass") is not None
                else None
            ),
            isMisclassified=document.get("isMisclassified"),
            confidenceScore=document.get("confidenceScore"),
            actionTaken=ActionTaken(document["actionTaken"]),
            imageFileId=document.get("imageFileId"),
            notes=document.get("notes"),
        )

    async def save(
        self,
        event: Event,
    ) -> Event:
        await self.collection.insert_one(
            self._toDocument(event)
        )

        return event

    async def findById(
        self,
        eventId: str,
    ) -> Event | None:
        document = await self.collection.find_one(
            {"eventId": eventId}
        )

        return (
            self._fromDocument(document)
            if document is not None
            else None
        )

    async def findAll(
        self,
        fromDate: datetime | None = None,
        toDate: datetime | None = None,
    ) -> list[Event]:
        query = self._buildDateQuery(
            fromDate=fromDate,
            toDate=toDate,
        )

        cursor = self.collection.find(query).sort(
            "timestamp", -1
        )

        return [
            self._fromDocument(document)
            async for document in cursor
        ]

    async def countByDetectedClass(
        self,
        fromDate: datetime | None = None,
        toDate: datetime | None = None,
    ) -> dict[DetectedClass, int]:
        query = self._buildDateQuery(
            fromDate=fromDate,
            toDate=toDate,
        )

        pipeline = []

        if query:
            pipeline.append({"$match": query})

        pipeline.append(
            {
                "$group": {
                    "_id": "$detectedClass",
                    "count": {"$sum": 1},
                }
            }
        )

        counts = {
            detectedClass: 0
            for detectedClass in DetectedClass
        }

        async for result in self.collection.aggregate(
            pipeline
        ):
            groupId = result["_id"]

            if groupId is not None:
                counts[DetectedClass(groupId)] = result[
                    "count"
                ]

        return counts

    async def updateImageFileId(
        self,
        eventId: str,
        imageFileId: str,
    ) -> None:
        await self.collection.update_one(
            {"eventId": eventId},
            {"$set": {"imageFileId": imageFileId}},
        )

    def _buildDateQuery(
        self,
        fromDate: datetime | None,
        toDate: datetime | None,
    ) -> dict:
        normalizedFromDate = self.normalizeDateTime(
            fromDate
        )
        normalizedToDate = self.normalizeDateTime(toDate)

        timestampQuery = {}

        if normalizedFromDate is not None:
            timestampQuery["$gte"] = normalizedFromDate

        if normalizedToDate is not None:
            timestampQuery["$lte"] = normalizedToDate

        return (
            {"timestamp": timestampQuery}
            if timestampQuery
            else {}
        )

    def normalizeDateTime(
        self,
        dateTime: datetime | None,
    ) -> datetime | None:
        if (
            dateTime is not None
            and dateTime.tzinfo is None
        ):
            return dateTime.replace(
                tzinfo=timezone.utc
            )

        return dateTime


eventRepository = EventRepository()
