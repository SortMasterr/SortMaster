"""Run SortMaster daily and weekly reports in a dedicated scheduler process."""

from __future__ import annotations

import logging
import os
import smtplib
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as datetimeTime
from pathlib import Path
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

from RPAs.reportAutomation.reportAutomation import (
    ConfigurationError,
    DuplicateReportError,
    ReportAutomationError,
    Settings,
    configureLogging,
    runReport,
)


weekdayNumbers = {
    "MON": 0,
    "TUE": 1,
    "WED": 2,
    "THU": 3,
    "FRI": 4,
    "SAT": 5,
    "SUN": 6,
}


@dataclass(frozen=True)
class SchedulerConfig:
    dailySendTime: datetimeTime
    weeklySendDay: int
    weeklySendTime: datetimeTime
    pollSeconds: float


def parseSendTime(value: str, settingName: str) -> datetimeTime:
    try:
        return datetime.strptime(value.strip(), "%H:%M").time()
    except ValueError as error:
        raise ConfigurationError(
            f"{settingName}은 HH:MM 형식이어야 합니다."
        ) from error


def loadSchedulerConfig() -> SchedulerConfig:
    weeklyDayText = os.getenv(
        "RPA_WEEKLY_SEND_DAY",
        "MON",
    ).strip().upper()
    if weeklyDayText not in weekdayNumbers:
        raise ConfigurationError(
            "RPA_WEEKLY_SEND_DAY는 MON~SUN 중 하나여야 합니다."
        )
    try:
        pollSeconds = float(
            os.getenv("RPA_SCHEDULER_POLL_SECONDS", "30")
        )
    except ValueError as error:
        raise ConfigurationError(
            "RPA_SCHEDULER_POLL_SECONDS는 숫자여야 합니다."
        ) from error
    if pollSeconds <= 0:
        raise ConfigurationError(
            "RPA_SCHEDULER_POLL_SECONDS는 0보다 커야 합니다."
        )
    return SchedulerConfig(
        dailySendTime=parseSendTime(
            os.getenv("RPA_DAILY_SEND_TIME", "09:00"),
            "RPA_DAILY_SEND_TIME",
        ),
        weeklySendDay=weekdayNumbers[weeklyDayText],
        weeklySendTime=parseSendTime(
            os.getenv("RPA_WEEKLY_SEND_TIME", "09:10"),
            "RPA_WEEKLY_SEND_TIME",
        ),
        pollSeconds=pollSeconds,
    )


def dueReportTypes(
    now: datetime,
    lastAttempts: dict[str, date],
    config: SchedulerConfig,
) -> tuple[str, ...]:
    due = []
    today = now.date()
    currentTime = now.time().replace(tzinfo=None)
    if (
        currentTime >= config.dailySendTime
        and lastAttempts.get("daily") != today
    ):
        due.append("daily")
    if (
        now.weekday() == config.weeklySendDay
        and currentTime >= config.weeklySendTime
        and lastAttempts.get("weekly") != today
    ):
        due.append("weekly")
    return tuple(due)


def initializeAttemptState(
    now: datetime,
    config: SchedulerConfig,
) -> dict[str, date]:
    return {
        reportType: now.date()
        for reportType in dueReportTypes(now, {}, config)
    }


def loadDotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    repositoryRoot = Path(__file__).resolve().parents[2]
    load_dotenv(repositoryRoot / ".env")


def runScheduler() -> None:
    loadDotenv()
    initialSettings = Settings.fromEnvironment(
        requireEmail=False,
        requireRecipients=False,
    )
    config = loadSchedulerConfig()
    configureLogging(initialSettings.stateDirectory)
    logger = logging.getLogger("reportScheduler")
    initialNow = datetime.now(
        ZoneInfo(initialSettings.timezoneName)
    )
    lastAttempts = initializeAttemptState(
        initialNow,
        config,
    )
    logger.info("status=STARTED")

    while True:
        settings = Settings.fromEnvironment(
            requireEmail=False,
            requireRecipients=False,
        )
        now = datetime.now(ZoneInfo(settings.timezoneName))
        dueReports = dueReportTypes(
            now,
            lastAttempts,
            config,
        )
        if not settings.enabled:
            for reportType in dueReports:
                lastAttempts[reportType] = now.date()
        else:
            for reportType in dueReports:
                lastAttempts[reportType] = now.date()
                try:
                    reportSettings = Settings.fromEnvironment()
                except ConfigurationError:
                    logger.warning(
                        "report=%s status=SKIPPED_NO_SETTINGS",
                        reportType,
                    )
                    continue

                try:
                    runReport(reportType, reportSettings, now=now)
                except DuplicateReportError:
                    logger.info(
                        "report=%s status=ALREADY_SENT",
                        reportType,
                    )
                except (
                    ReportAutomationError,
                    ValueError,
                    HTTPError,
                    smtplib.SMTPException,
                    OSError,
                ) as error:
                    logger.error(
                        "report=%s status=FAILED errorType=%s",
                        reportType,
                        type(error).__name__,
                    )
        time.sleep(config.pollSeconds)


def main() -> int:
    try:
        runScheduler()
    except KeyboardInterrupt:
        return 0
    except (ConfigurationError, OSError) as error:
        logging.getLogger("reportScheduler").error(
            "status=FAILED errorType=%s",
            type(error).__name__,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
