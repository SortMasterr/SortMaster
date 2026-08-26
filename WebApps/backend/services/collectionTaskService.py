import logging
from datetime import datetime, time, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from repositories.collectionAutomationRepository import (
    CollectionAutomationRepository,
    collectionAutomationRepository,
)
from repositories.collectionTaskRepository import (
    CollectionTaskRepository,
    collectionTaskRepository,
)
from schemas.collectionTask import (
    CollectionAutomationStatus,
    CollectionAutomationActionType,
    CollectionRunStatus,
    CollectionTask,
    CollectionTaskList,
    CollectionTaskStatus,
)
from schemas.event import Event
from services.collectionAutomationConfig import CollectionAutomationConfig
from RPAs.reportAutomation.reportAutomation import ConfigurationError


logger = logging.getLogger(__name__)


class CollectionTaskNotFoundError(KeyError):
    pass


class CollectionTaskConflictError(ValueError):
    pass


class CollectionTaskService:
    def __init__(
        self,
        repository: CollectionTaskRepository,
        automationRepository: CollectionAutomationRepository,
    ):
        self.repository = repository
        self.automationRepository = automationRepository

    async def createForOverflow(self, event: Event) -> tuple[CollectionTask, bool] | None:
        try:
            config = CollectionAutomationConfig.fromEnvironment()
        except ConfigurationError as error:
            logger.error(
                "collection automation configuration is invalid: %s",
                error,
            )
            return None
        if not config.enabled:
            return None
        task = CollectionTask(
            collectionTaskId=str(uuid4()),
            binId=event.binId,
            binType=event.binType,
            cameraId=event.cameraId,
            relatedEventId=event.eventId,
            taskStatus=CollectionTaskStatus.OPEN,
            detectedAt=event.timestamp,
            createdAt=datetime.now(timezone.utc),
        )
        savedTask, created = await self.repository.create(task)
        await self.automationRepository.recordRun(
            savedTask.collectionTaskId,
            (
                CollectionAutomationActionType.TASK_CREATED
                if created
                else CollectionAutomationActionType.TASK_DUPLICATE_SKIPPED
            ),
            CollectionRunStatus.SUCCESS,
            datetime.now(timezone.utc),
            "system",
        )
        return savedTask, created

    async def getTasks(
        self,
        taskStatus: CollectionTaskStatus | None,
        limit: int,
    ) -> CollectionTaskList:
        tasks, total = await self.repository.findAll(taskStatus, limit)
        return CollectionTaskList(tasks=tasks, total=total)

    async def acknowledge(self, collectionTaskId: str) -> CollectionTask:
        task = await self._requireActive(collectionTaskId)
        if task.taskStatus == CollectionTaskStatus.ACKNOWLEDGED:
            return task
        updated = await self.repository.updateFields(collectionTaskId, {
            "taskStatus": CollectionTaskStatus.ACKNOWLEDGED,
            "acknowledgedAt": datetime.now(timezone.utc),
        })
        result = self._requireUpdated(updated)
        await self.automationRepository.recordRun(
            collectionTaskId,
            CollectionAutomationActionType.ACKNOWLEDGED,
            CollectionRunStatus.SUCCESS,
            datetime.now(timezone.utc),
            "operator",
        )
        return result

    async def complete(self, collectionTaskId: str) -> CollectionTask:
        task = await self._requireActive(collectionTaskId)
        completedAt = datetime.now(timezone.utc)
        updated = await self.repository.updateFields(collectionTaskId, {
            "taskStatus": CollectionTaskStatus.COMPLETED,
            "completedAt": completedAt,
            "processingSeconds": max(
                0.0,
                (completedAt - task.createdAt).total_seconds(),
            ),
            "nextNotificationAttemptAt": None,
            "lastFailureReason": None,
        })
        result = self._requireUpdated(updated)
        await self.automationRepository.recordRun(
            collectionTaskId,
            CollectionAutomationActionType.COMPLETED,
            CollectionRunStatus.SUCCESS,
            completedAt,
            "operator",
        )
        return result

    async def getAutomationStatus(self) -> CollectionAutomationStatus:
        config = CollectionAutomationConfig.fromEnvironment()
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        todayStart = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo).astimezone(timezone.utc)
        metrics = await self.repository.getMetrics(todayStart)
        state = await self.automationRepository.getState()
        lastHeartbeatAt = state.get("lastHeartbeatAt") if state else None
        workerStatus = state.get("workerStatus", "NOT_STARTED") if state else "NOT_STARTED"
        if (
            config.enabled
            and lastHeartbeatAt is not None
            and (datetime.now(timezone.utc) - lastHeartbeatAt).total_seconds()
            > max(config.pollSeconds * 2, 60)
        ):
            workerStatus = "STALE"
        return CollectionAutomationStatus(
            enabled=config.enabled,
            assigneeConfigured=config.assigneeEmail is not None,
            managerConfigured=config.managerEmail is not None,
            lastHeartbeatAt=lastHeartbeatAt,
            workerStatus=workerStatus,
            recentRuns=await self.automationRepository.recentRuns(),
            **metrics,
        )

    async def _requireActive(self, collectionTaskId: str) -> CollectionTask:
        task = await self.repository.findById(collectionTaskId)
        if task is None:
            raise CollectionTaskNotFoundError(collectionTaskId)
        if task.taskStatus in {CollectionTaskStatus.COMPLETED, CollectionTaskStatus.CANCELLED}:
            raise CollectionTaskConflictError("이미 종료된 수거 작업입니다.")
        return task

    @staticmethod
    def _requireUpdated(task: CollectionTask | None) -> CollectionTask:
        if task is None:
            raise CollectionTaskNotFoundError()
        return task


collectionTaskService = CollectionTaskService(
    collectionTaskRepository,
    collectionAutomationRepository,
)
