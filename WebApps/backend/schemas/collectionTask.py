from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from schemas.event import BinType, CameraId


class CollectionTaskStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class CollectionAutomationActionType(str, Enum):
    TASK_CREATED = "TASK_CREATED"
    TASK_DUPLICATE_SKIPPED = "TASK_DUPLICATE_SKIPPED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    COMPLETED = "COMPLETED"
    INITIAL = "INITIAL"
    REMINDER = "REMINDER"
    ESCALATION = "ESCALATION"


class CollectionRunStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class CollectionTask(BaseModel):
    collectionTaskId: str
    binId: str
    binType: BinType
    cameraId: CameraId
    relatedEventId: str
    taskStatus: CollectionTaskStatus
    detectedAt: datetime
    createdAt: datetime
    acknowledgedAt: datetime | None = None
    completedAt: datetime | None = None
    processingSeconds: float | None = Field(default=None, ge=0.0)
    escalationLevel: int = Field(default=0, ge=0, le=2)
    initialNotificationAt: datetime | None = None
    reminderNotificationAt: datetime | None = None
    escalationNotificationAt: datetime | None = None
    lastNotificationAt: datetime | None = None
    notificationAttemptCount: int = Field(default=0, ge=0)
    nextNotificationAttemptAt: datetime | None = None
    lastFailureReason: str | None = None


class CollectionTaskList(BaseModel):
    tasks: list[CollectionTask]
    total: int


class CollectionAutomationRun(BaseModel):
    runId: str
    collectionTaskId: str
    actionType: CollectionAutomationActionType
    status: CollectionRunStatus
    attemptedAt: datetime
    recipientRole: str
    errorType: str | None = None


class CollectionAutomationStatus(BaseModel):
    enabled: bool
    assigneeConfigured: bool
    managerConfigured: bool
    lastHeartbeatAt: datetime | None = None
    workerStatus: str
    openTaskCount: int
    acknowledgedTaskCount: int
    escalatedTaskCount: int
    completedTodayCount: int
    averageProcessingSeconds: float | None = None
    recentRuns: list[CollectionAutomationRun]
