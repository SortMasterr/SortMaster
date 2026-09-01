from __future__ import annotations

import asyncio
import logging
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo


repositoryRoot = Path(__file__).resolve().parents[2]
backendPath = repositoryRoot / "WebApps" / "backend"
for path in (repositoryRoot, backendPath):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from repositories.collectionAutomationRepository import (  # noqa: E402
    collectionAutomationRepository,
)
from repositories.collectionTaskRepository import (  # noqa: E402
    collectionTaskRepository,
)
from repositories.mongoClient import closeMongoClient, pingMongo  # noqa: E402
from schemas.collectionTask import (  # noqa: E402
    CollectionAutomationActionType,
    CollectionRunStatus,
    CollectionTask,
)
from services.collectionAutomationConfig import (  # noqa: E402
    CollectionAutomationConfig,
)
from RPAs.reportAutomation.reportAutomation import (  # noqa: E402
    ConfigurationError,
    Settings,
)


logger = logging.getLogger("collectionScheduler")


def buildMessage(
    task: CollectionTask,
    actionType: CollectionAutomationActionType,
    sender: str,
    timezoneName: str,
) -> EmailMessage:
    titles = {
        CollectionAutomationActionType.INITIAL: "쓰레기통 수거 요청",
        CollectionAutomationActionType.REMINDER: "쓰레기통 수거 재알림",
        CollectionAutomationActionType.ESCALATION: "[긴급] 수거 작업 미처리 알림",
    }
    elapsedMinutes = max(
        0,
        int((datetime.now(timezone.utc) - task.createdAt).total_seconds() // 60),
    )
    message = EmailMessage()
    message["Subject"] = f"[SortMaster] {titles[actionType]}"
    message["From"] = sender
    message.set_content(
        "\n".join([
            titles[actionType],
            "",
            f"쓰레기통 ID: {task.binId}",
            f"쓰레기통 종류: {task.binType.value}",
            f"감지 시각: {task.detectedAt.astimezone(ZoneInfo(timezoneName)).strftime('%Y-%m-%d %H:%M:%S')}",
            f"현재 작업 상태: {task.taskStatus.value}",
            f"경과 시간: {elapsedMinutes}분",
            f"작업 ID: {task.collectionTaskId}",
            "",
            "SortMaster 통계 대시보드에서 작업을 확인하고 수거 완료 처리해 주세요.",
        ])
    )
    return message


def sendMessage(message: EmailMessage, recipient: str, settings: Settings) -> None:
    message["To"] = recipient
    with smtplib.SMTP(
        settings.smtpHost,
        settings.smtpPort,
        timeout=settings.requestTimeoutSeconds,
    ) as smtp:
        if settings.smtpUseTls:
            smtp.starttls()
        smtp.login(settings.smtpUser, settings.smtpPassword)
        smtp.send_message(message, from_addr=settings.sender, to_addrs=(recipient,))


def selectNotification(
    task: CollectionTask,
    now: datetime,
    config: CollectionAutomationConfig,
) -> tuple[CollectionAutomationActionType, str, str] | None:
    elapsedMinutes = (now - task.createdAt).total_seconds() / 60
    if task.initialNotificationAt is None:
        if elapsedMinutes < config.initialDelayMinutes:
            return None
        return CollectionAutomationActionType.INITIAL, "assignee", config.assigneeEmail or ""

    elapsedSinceInitialMinutes = (
        now - task.initialNotificationAt
    ).total_seconds() / 60

    if task.reminderNotificationAt is None:
        if elapsedSinceInitialMinutes < config.reminderMinutes:
            return None
        return CollectionAutomationActionType.REMINDER, "assignee", config.assigneeEmail or ""

    if (
        task.escalationNotificationAt is None
        and elapsedSinceInitialMinutes >= config.escalationMinutes
    ):
        return CollectionAutomationActionType.ESCALATION, "manager", config.managerEmail or ""
    return None


async def processTask(
    task: CollectionTask,
    now: datetime,
    config: CollectionAutomationConfig,
) -> None:
    selected = selectNotification(task, now, config)
    if selected is None:
        return
    actionType, recipientRole, recipient = selected
    try:
        if not recipient:
            raise ConfigurationError(f"{recipientRole} 이메일이 설정되지 않았습니다.")
        settings = Settings.fromEnvironment(requireEmail=True, requireRecipients=False)
        message = buildMessage(
            task,
            actionType,
            settings.sender,
            settings.timezoneName,
        )
        await asyncio.to_thread(sendMessage, message, recipient, settings)
    except (ConfigurationError, smtplib.SMTPException, OSError) as error:
        await collectionTaskRepository.updateFields(task.collectionTaskId, {
            "notificationAttemptCount": task.notificationAttemptCount + 1,
            "nextNotificationAttemptAt": now + timedelta(seconds=config.retrySeconds),
            "lastFailureReason": type(error).__name__,
        })
        await collectionAutomationRepository.recordRun(
            task.collectionTaskId,
            actionType,
            CollectionRunStatus.FAILED,
            now,
            recipientRole,
            type(error).__name__,
        )
        logger.error(
            "task=%s notification=%s status=FAILED errorType=%s",
            task.collectionTaskId,
            actionType.value,
            type(error).__name__,
        )
        return

    timestampField = {
        CollectionAutomationActionType.INITIAL: "initialNotificationAt",
        CollectionAutomationActionType.REMINDER: "reminderNotificationAt",
        CollectionAutomationActionType.ESCALATION: "escalationNotificationAt",
    }[actionType]
    escalationLevel = {
        CollectionAutomationActionType.INITIAL: 0,
        CollectionAutomationActionType.REMINDER: 1,
        CollectionAutomationActionType.ESCALATION: 2,
    }[actionType]
    await collectionTaskRepository.updateFields(task.collectionTaskId, {
        timestampField: now,
        "lastNotificationAt": now,
        "notificationAttemptCount": task.notificationAttemptCount + 1,
        "nextNotificationAttemptAt": None,
        "lastFailureReason": None,
        "escalationLevel": escalationLevel,
    })
    await collectionAutomationRepository.recordRun(
        task.collectionTaskId,
        actionType,
        CollectionRunStatus.SUCCESS,
        now,
        recipientRole,
    )
    logger.info(
        "task=%s notification=%s status=SUCCESS",
        task.collectionTaskId,
        actionType.value,
    )


async def runScheduler() -> None:
    logging.basicConfig(level=logging.INFO)
    await pingMongo()
    await collectionTaskRepository.ensureIndexes()
    logger.info("status=STARTED")
    while True:
        config = CollectionAutomationConfig.fromEnvironment()
        now = datetime.now(timezone.utc)
        workerStatus = "RUNNING" if config.enabled else "DISABLED"
        await collectionAutomationRepository.heartbeat(now, workerStatus)
        if config.enabled:
            for task in await collectionTaskRepository.findActionable(now):
                await processTask(task, now, config)
        await asyncio.sleep(config.pollSeconds)


def main() -> int:
    try:
        asyncio.run(runScheduler())
    except KeyboardInterrupt:
        return 0
    except (ConfigurationError, OSError) as error:
        logger.error("status=FAILED errorType=%s", type(error).__name__)
        return 1
    finally:
        closeMongoClient()
    return 0


if __name__ == "__main__":
    sys.exit(main())
