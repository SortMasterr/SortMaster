from datetime import datetime, timezone
from uuid import uuid4

from pymongo import DESCENDING

from repositories.mongoClient import getMongoDb
from schemas.collectionTask import (
    CollectionAutomationRun,
    CollectionAutomationActionType,
    CollectionRunStatus,
)


class CollectionAutomationRepository:
    @property
    def runs(self):
        return getMongoDb()["collectionAutomationRuns"]

    @property
    def state(self):
        return getMongoDb()["collectionAutomationState"]

    async def recordRun(
        self,
        collectionTaskId: str,
        actionType: CollectionAutomationActionType,
        status: CollectionRunStatus,
        attemptedAt: datetime,
        recipientRole: str,
        errorType: str | None = None,
    ) -> CollectionAutomationRun:
        run = CollectionAutomationRun(
            runId=str(uuid4()),
            collectionTaskId=collectionTaskId,
            actionType=actionType,
            status=status,
            attemptedAt=attemptedAt,
            recipientRole=recipientRole,
            errorType=errorType,
        )
        document = run.model_dump()
        document["actionType"] = actionType.value
        document["status"] = status.value
        await self.runs.insert_one(document)
        return run

    async def recentRuns(self, limit: int = 10) -> list[CollectionAutomationRun]:
        cursor = self.runs.find({}).sort("attemptedAt", DESCENDING).limit(limit)
        results = []
        async for document in cursor:
            results.append(CollectionAutomationRun(
                runId=document["runId"],
                collectionTaskId=document["collectionTaskId"],
                actionType=CollectionAutomationActionType(document["actionType"]),
                status=CollectionRunStatus(document["status"]),
                attemptedAt=self._normalizeDateTime(document["attemptedAt"]),
                recipientRole=document["recipientRole"],
                errorType=document.get("errorType"),
            ))
        return results

    async def heartbeat(self, at: datetime, workerStatus: str) -> None:
        await self.state.update_one(
            {"stateId": "collectionScheduler"},
            {"$set": {"lastHeartbeatAt": at, "workerStatus": workerStatus}},
            upsert=True,
        )

    async def getState(self) -> dict | None:
        document = await self.state.find_one({"stateId": "collectionScheduler"})
        if document and document.get("lastHeartbeatAt"):
            document["lastHeartbeatAt"] = self._normalizeDateTime(
                document["lastHeartbeatAt"]
            )
        return document

    @staticmethod
    def _normalizeDateTime(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


collectionAutomationRepository = CollectionAutomationRepository()
