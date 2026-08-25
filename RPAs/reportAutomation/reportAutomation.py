"""SortMaster daily/weekly report automation.

This process reads the public REST API only. It never connects to MongoDB and is
launched by the dedicated Docker scheduler, Windows Task Scheduler, or cron.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import logging
import os
import re
import smtplib
import socket
import ssl
import sys
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time as datetimeTime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ReportAutomationError(Exception):
    """Base error for a report run."""


class ConfigurationError(ReportAutomationError):
    """Environment configuration is invalid."""


class ApiResponseError(ReportAutomationError):
    """The backend returned an invalid response."""


class DataMismatchError(ReportAutomationError):
    """Statistics and event-list data do not agree."""


class DuplicateReportError(ReportAutomationError):
    """This execution key has already been sent."""


class LockUnavailableError(ReportAutomationError):
    """Another process owns the report execution lock."""


class SmtpAuthenticationError(ReportAutomationError):
    """SMTP credentials were rejected and should not be retried."""


CLASS_NAMES = {
    "normal": "일반 쓰레기",
    "paper": "종이",
    "recyclables": "플라스틱·캔",
    "coffeeCup": "커피 컵",
}
BIN_NAMES = {
    "normal": "일반 수거함",
    "paper": "종이 수거함",
    "recyclables": "플라스틱·캔 수거함",
    "coffeeCup": "커피 컵 수거함",
}
EVENT_NAMES = {
    "misclassification": "오분류",
    "overflow": "넘침",
}
ACTION_NAMES = {
    "lightAndSound": "전구+경고음",
    "soundOnly": "경고음",
    "lightOnly": "전구",
    "notificationOnly": "알림",
    "none": "알림 없음",
}
CSV_FIELDS = (
    "eventId",
    "timestampKst",
    "cameraId",
    "eventCategory",
    "detectedClass",
    "binId",
    "binType",
    "confidenceScore",
    "actionTaken",
    "modelVersion",
    "imageFileId",
)
REQUIRED_EVENT_FIELDS = (
    "eventId",
    "timestamp",
    "cameraId",
    "eventCategory",
    "binId",
    "binType",
    "actionTaken",
    "modelVersion",
)


def normalizeEmailAddress(value: str) -> str:
    normalized = value.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
        raise ConfigurationError("올바른 수신 이메일 주소가 설정되지 않았습니다.")
    return normalized


class RecipientSettingsStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.settingsPath = directory / "recipientSettings.json"

    def loadRecipient(self) -> str | None:
        if not self.settingsPath.exists():
            return None
        try:
            data = json.loads(self.settingsPath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigurationError(
                "수신 이메일 설정을 읽을 수 없습니다."
            ) from error
        if not isinstance(data, dict) or not isinstance(
            data.get("recipient"),
            str,
        ):
            raise ConfigurationError(
                "수신 이메일 설정 파일 형식이 잘못되었습니다."
            )
        return normalizeEmailAddress(data["recipient"])

    def saveRecipient(self, recipient: str) -> str:
        normalized = normalizeEmailAddress(recipient)
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.settingsPath.with_suffix(".tmp")
        payload = {
            "recipient": normalized,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.settingsPath)
        except OSError as error:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise ConfigurationError(
                "수신 이메일 설정을 저장할 수 없습니다."
            ) from error
        return normalized


@dataclass(frozen=True)
class ReportPeriod:
    reportType: str
    startKst: datetime
    endKst: datetime
    startUtc: datetime
    endUtc: datetime

    @property
    def dateLabel(self) -> str:
        if self.reportType == "daily":
            return self.startKst.date().isoformat()
        return f"{self.startKst.date().isoformat()}~{self.endKst.date().isoformat()}"

    @property
    def fileLabel(self) -> str:
        if self.reportType == "daily":
            return self.startKst.date().isoformat()
        return f"{self.startKst.date().isoformat()}_{self.endKst.date().isoformat()}"


@dataclass(frozen=True)
class Settings:
    enabled: bool
    timezoneName: str
    recipients: tuple[str, ...]
    recipientGroup: str
    sender: str
    smtpHost: str
    smtpPort: int
    smtpUser: str
    smtpPassword: str
    smtpUseTls: bool
    apiBaseUrl: str
    webBaseUrl: str
    retryDelays: tuple[float, ...]
    requestTimeoutSeconds: float
    stateDirectory: Path
    outputDirectory: Path

    @classmethod
    def fromEnvironment(
        cls,
        requireEmail: bool = True,
        requireRecipients: bool = True,
    ) -> "Settings":
        baseDirectory = Path(__file__).resolve().parent
        stateDirectory = Path(
            os.getenv(
                "RPA_STATE_DIRECTORY",
                str(baseDirectory / "state"),
            )
        )
        environmentRecipients = tuple(
            item.strip()
            for item in os.getenv("RPA_REPORT_RECIPIENTS", "").split(",")
            if item.strip()
        )
        storedRecipient = RecipientSettingsStore(
            stateDirectory
        ).loadRecipient()
        recipients = (
            (storedRecipient,)
            if storedRecipient
            else environmentRecipients
        )
        sender = os.getenv("RPA_REPORT_FROM", "").strip()
        smtpHost = os.getenv("SMTP_HOST", "").strip()
        smtpUser = os.getenv("SMTP_USER", "").strip()
        smtpPassword = os.getenv("SMTP_PASSWORD", "")
        missing = []
        if requireEmail:
            requiredEmailSettings = [
                ("RPA_REPORT_FROM", sender),
                ("SMTP_HOST", smtpHost),
                ("SMTP_USER", smtpUser),
                ("SMTP_PASSWORD", smtpPassword),
            ]
            if requireRecipients:
                requiredEmailSettings.insert(
                    0,
                    ("RPA_REPORT_RECIPIENTS", recipients),
                )
            for name, value in requiredEmailSettings:
                if not value:
                    missing.append(name)
        if missing:
            raise ConfigurationError(f"필수 환경변수 누락: {', '.join(missing)}")
        if requireEmail and smtpHost.lower() == "smtp.gmail.com":
            normalizedSender = normalizeEmailAddress(sender)
            normalizedUser = normalizeEmailAddress(smtpUser)
            if normalizedSender != normalizedUser:
                raise ConfigurationError(
                    "Gmail SMTP_USER는 RPA_REPORT_FROM과 같은 전체 이메일 주소여야 합니다."
                )

        timezoneName = os.getenv("RPA_REPORT_TIMEZONE", "Asia/Seoul").strip()
        try:
            ZoneInfo(timezoneName)
        except ZoneInfoNotFoundError as error:
            raise ConfigurationError(f"지원하지 않는 시간대: {timezoneName}") from error

        retryText = os.getenv("RPA_RETRY_DELAYS_SECONDS", "60,300,900")
        try:
            retryDelays = tuple(float(item.strip()) for item in retryText.split(",") if item.strip())
            smtpPort = int(os.getenv("SMTP_PORT", "587"))
            timeout = float(os.getenv("RPA_REQUEST_TIMEOUT_SECONDS", "15"))
        except ValueError as error:
            raise ConfigurationError("포트, 제한 시간 또는 재시도 간격 설정이 숫자가 아닙니다.") from error
        if any(delay < 0 for delay in retryDelays) or timeout <= 0:
            raise ConfigurationError("재시도 간격은 0 이상, 요청 제한 시간은 0보다 커야 합니다.")

        return cls(
            enabled=_parseBool(os.getenv("RPA_REPORT_ENABLED", "true")),
            timezoneName=timezoneName,
            recipients=recipients,
            recipientGroup=os.getenv("RPA_REPORT_RECIPIENT_GROUP", "operations").strip() or "operations",
            sender=sender,
            smtpHost=smtpHost,
            smtpPort=smtpPort,
            smtpUser=smtpUser,
            smtpPassword=smtpPassword,
            smtpUseTls=_parseBool(os.getenv("SMTP_USE_TLS", "true")),
            apiBaseUrl=os.getenv("SORTMASTER_API_BASE_URL", "http://localhost:8047").rstrip("/"),
            webBaseUrl=os.getenv("SORTMASTER_WEB_BASE_URL", "http://localhost:8047").rstrip("/"),
            retryDelays=retryDelays,
            requestTimeoutSeconds=timeout,
            stateDirectory=stateDirectory,
            outputDirectory=Path(os.getenv("RPA_OUTPUT_DIRECTORY", str(baseDirectory / "output"))),
        )


def _parseBool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"boolean 환경변수 값이 잘못되었습니다: {value!r}")


def calculatePeriod(
    reportType: str,
    now: datetime | None = None,
    timezoneName: str = "Asia/Seoul",
    targetDate: date | None = None,
) -> ReportPeriod:
    if reportType not in {"daily", "weekly"}:
        raise ValueError("reportType은 daily 또는 weekly여야 합니다.")
    reportTimezone = ZoneInfo(timezoneName)
    current = now or datetime.now(reportTimezone)
    if current.tzinfo is None:
        current = current.replace(tzinfo=reportTimezone)
    else:
        current = current.astimezone(reportTimezone)

    if targetDate is not None:
        startDate = targetDate
    elif reportType == "daily":
        startDate = current.date() - timedelta(days=1)
    else:
        thisMonday = current.date() - timedelta(days=current.weekday())
        startDate = thisMonday - timedelta(days=7)
    endDate = startDate if reportType == "daily" else startDate + timedelta(days=6)
    startKst = datetime.combine(startDate, datetimeTime.min, reportTimezone)
    endKst = datetime.combine(endDate, datetimeTime.max, reportTimezone)
    return ReportPeriod(
        reportType=reportType,
        startKst=startKst,
        endKst=endKst,
        startUtc=startKst.astimezone(timezone.utc),
        endUtc=endKst.astimezone(timezone.utc),
    )


def previousPeriod(period: ReportPeriod) -> ReportPeriod:
    days = 1 if period.reportType == "daily" else 7
    return calculatePeriod(
        period.reportType,
        timezoneName=period.startKst.tzinfo.key,
        targetDate=period.startKst.date() - timedelta(days=days),
    )


class ApiClient:
    def __init__(self, baseUrl: str, timeoutSeconds: float = 15):
        self.baseUrl = baseUrl.rstrip("/")
        self.timeoutSeconds = timeoutSeconds

    def getReportData(self, period: ReportPeriod) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        query = urlencode(
            {
                "from": period.startUtc.isoformat().replace("+00:00", "Z"),
                "to": period.endUtc.isoformat().replace("+00:00", "Z"),
            }
        )
        statistics = self._getJson(f"/api/statistics?{query}")
        events = self._getJson(f"/api/events?{query}")
        if not isinstance(statistics, dict):
            raise ApiResponseError("통계 API 응답이 객체가 아닙니다.")
        if not isinstance(events, list):
            raise ApiResponseError("이벤트 API 응답이 배열이 아닙니다.")
        return statistics, events

    def _getJson(self, path: str) -> Any:
        request = Request(f"{self.baseUrl}{path}", headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeoutSeconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return json.loads(response.read().decode(charset))
        except HTTPError as error:
            message = f"API HTTP 오류: status={error.code} path={path.split('?', 1)[0]}"
            if error.code == 422 or 400 <= error.code < 500:
                raise ApiResponseError(message) from error
            raise ConnectionError(message) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            raise ConnectionError(f"API 연결 실패: path={path.split('?', 1)[0]}") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ApiResponseError("API 응답을 JSON으로 해석할 수 없습니다.") from error


def _isNonNegativeInteger(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def parseTimestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ApiResponseError("이벤트 timestamp가 문자열이 아닙니다.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ApiResponseError(f"이벤트 timestamp 형식 오류: {value!r}") from error
    if parsed.tzinfo is None:
        raise ApiResponseError("이벤트 timestamp에는 UTC offset이 필요합니다.")
    return parsed.astimezone(timezone.utc)


def validateData(
    statistics: dict[str, Any],
    events: list[dict[str, Any]],
    period: ReportPeriod,
) -> None:
    requiredStatistics = (
        "labels",
        "counts",
        "totalEventCount",
        "misclassificationCount",
        "overflowCount",
    )
    missing = [field for field in requiredStatistics if field not in statistics]
    if missing:
        raise ApiResponseError(f"통계 API 필드 누락: {', '.join(missing)}")
    labels = statistics["labels"]
    counts = statistics["counts"]
    if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
        raise ApiResponseError("statistics.labels는 문자열 배열이어야 합니다.")
    if not isinstance(counts, list) or len(labels) != len(counts):
        raise ApiResponseError("statistics.labels와 counts의 길이가 다릅니다.")
    if len(set(labels)) != len(labels) or any(label not in CLASS_NAMES for label in labels):
        raise ApiResponseError("statistics.labels에 중복 또는 지원하지 않는 클래스가 있습니다.")
    numericValues = list(counts) + [
        statistics["totalEventCount"],
        statistics["misclassificationCount"],
        statistics["overflowCount"],
    ]
    if not all(_isNonNegativeInteger(value) for value in numericValues):
        raise ApiResponseError("모든 통계 건수는 0 이상의 정수여야 합니다.")
    if statistics["totalEventCount"] != (
        statistics["misclassificationCount"] + statistics["overflowCount"]
    ):
        raise DataMismatchError("전체 이벤트 수가 오분류 수와 넘침 수의 합과 다릅니다.")

    categoryCounts = Counter()
    classCounts = Counter()
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ApiResponseError(f"events[{index}]가 객체가 아닙니다.")
        eventMissing = [field for field in REQUIRED_EVENT_FIELDS if field not in event]
        if eventMissing:
            raise ApiResponseError(f"events[{index}] 필드 누락: {', '.join(eventMissing)}")
        timestamp = parseTimestamp(event["timestamp"])
        if not period.startUtc <= timestamp <= period.endUtc:
            raise DataMismatchError(f"events[{index}]의 시간이 요청 범위를 벗어났습니다.")
        category = event["eventCategory"]
        if category not in EVENT_NAMES:
            raise ApiResponseError(f"events[{index}]의 eventCategory가 잘못되었습니다.")
        if event["binType"] not in BIN_NAMES:
            raise ApiResponseError(f"events[{index}]의 binType이 잘못되었습니다.")
        if event["actionTaken"] not in ACTION_NAMES:
            raise ApiResponseError(f"events[{index}]의 actionTaken이 잘못되었습니다.")
        categoryCounts[category] += 1
        if category == "misclassification":
            detectedClass = event.get("detectedClass")
            confidence = event.get("confidenceScore")
            if detectedClass not in CLASS_NAMES:
                raise ApiResponseError(f"events[{index}]의 detectedClass가 잘못되었습니다.")
            if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
                raise ApiResponseError(f"events[{index}]의 confidenceScore가 잘못되었습니다.")
            classCounts[detectedClass] += 1
        elif event.get("detectedClass") is not None or event.get("confidenceScore") is not None:
            raise ApiResponseError(f"events[{index}] overflow 이벤트의 분류 필드는 null이어야 합니다.")

    expectedCategories = {
        "misclassification": statistics["misclassificationCount"],
        "overflow": statistics["overflowCount"],
    }
    if len(events) != statistics["totalEventCount"] or any(
        categoryCounts[name] != count for name, count in expectedCategories.items()
    ):
        raise DataMismatchError("통계 API와 이벤트 API의 카테고리별 합계가 다릅니다.")
    statisticsByClass = dict(zip(labels, counts))
    if any(classCounts[label] != statisticsByClass.get(label, 0) for label in CLASS_NAMES):
        raise DataMismatchError("통계 API와 이벤트 API의 클래스별 합계가 다릅니다.")


def aggregateData(
    statistics: dict[str, Any],
    events: list[dict[str, Any]],
    period: ReportPeriod,
) -> dict[str, Any]:
    reportTimezone = period.startKst.tzinfo
    classCounts = {label: 0 for label in CLASS_NAMES}
    classCounts.update(dict(zip(statistics["labels"], statistics["counts"])))
    binCounts: dict[str, Counter[str]] = {}
    confidences = []
    for event in events:
        binKey = event["binType"]
        counts = binCounts.setdefault(binKey, Counter())
        counts[event["eventCategory"]] += 1
        counts["total"] += 1
        if event["eventCategory"] == "misclassification":
            confidences.append(float(event["confidenceScore"]))

    if period.reportType == "daily":
        timeline = [
            {"label": f"{hour:02d}:00~{hour:02d}:59", "misclassification": 0, "overflow": 0, "total": 0}
            for hour in range(24)
        ]
        for event in events:
            local = parseTimestamp(event["timestamp"]).astimezone(reportTimezone)
            timeline[local.hour][event["eventCategory"]] += 1
            timeline[local.hour]["total"] += 1
    else:
        weekdayNames = ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일")
        timeline = [
            {"label": name, "misclassification": 0, "overflow": 0, "total": 0}
            for name in weekdayNames
        ]
        for event in events:
            local = parseTimestamp(event["timestamp"]).astimezone(reportTimezone)
            timeline[local.weekday()][event["eventCategory"]] += 1
            timeline[local.weekday()]["total"] += 1

    maxClassCount = max(classCounts.values(), default=0)
    topClasses = [name for name, count in classCounts.items() if count == maxClassCount and count > 0]
    maxBinCount = max((counts["total"] for counts in binCounts.values()), default=0)
    topBins = [name for name, counts in binCounts.items() if counts["total"] == maxBinCount and maxBinCount > 0]
    recentEvents = sorted(events, key=lambda event: parseTimestamp(event["timestamp"]), reverse=True)[:10]
    return {
        "statistics": statistics,
        "classCounts": classCounts,
        "binCounts": binCounts,
        "timeline": timeline,
        "topClasses": topClasses,
        "topClassCount": maxClassCount,
        "topBins": topBins,
        "topBinCount": maxBinCount,
        "averageConfidence": (sum(confidences) / len(confidences)) if confidences else None,
        "recentEvents": recentEvents,
    }


def _summaryText(data: dict[str, Any]) -> str:
    statistics = data["statistics"]
    if statistics["totalEventCount"] == 0:
        return (
            "조회 기간 동안 저장된 오분류 및 넘침 이벤트가 없습니다. "
            "본 보고서는 정상적으로 생성되었으며, 해당 기간의 집계 결과는 0건입니다."
        )
    sentences = [
        f"조회 기간 동안 총 {statistics['totalEventCount']}건의 이상 이벤트가 기록되었습니다.",
        f"오분류 이벤트는 {statistics['misclassificationCount']}건, 넘침 이벤트는 {statistics['overflowCount']}건입니다.",
    ]
    if data["topClasses"]:
        names = "와 ".join(CLASS_NAMES[name] for name in data["topClasses"])
        qualifier = "각각 " if len(data["topClasses"]) > 1 else "총 "
        sentences.append(f"가장 많이 발생한 오분류 클래스는 {names}으로 {qualifier}{data['topClassCount']}건입니다.")
    if data["topBins"]:
        names = "와 ".join(BIN_NAMES.get(name, name) for name in data["topBins"])
        qualifier = "각각 " if len(data["topBins"]) > 1 else "총 "
        sentences.append(f"가장 많은 이벤트가 발생한 수거함은 {names}으로 {qualifier}{data['topBinCount']}건입니다.")
    return " ".join(sentences)


def _table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    headerHtml = "".join(f"<th>{html.escape(str(value))}</th>" for value in headers)
    rowsHtml = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{headerHtml}</tr></thead><tbody>{rowsHtml}</tbody></table>"


def _changeText(current: int, previous: int) -> str:
    difference = current - previous
    if difference == 0:
        return "변동 없음"
    if previous == 0:
        return f"신규 발생 (+{current}건)"
    rate = abs(difference) / previous * 100
    direction = "증가" if difference > 0 else "감소"
    sign = "+" if difference > 0 else "-"
    return f"{sign}{abs(difference)}건 ({rate:.1f}% {direction})"


def buildHtml(
    data: dict[str, Any],
    period: ReportPeriod,
    webBaseUrl: str,
    previousData: dict[str, Any] | None = None,
    generatedAt: datetime | None = None,
) -> str:
    statistics = data["statistics"]
    generated = (generatedAt or datetime.now(period.startKst.tzinfo)).astimezone(period.startKst.tzinfo)
    reportName = "일일" if period.reportType == "daily" else "주간"
    average = "-" if data["averageConfidence"] is None else f"{data['averageConfidence'] * 100:.1f}%"
    topClass = "-" if not data["topClasses"] else f"{'·'.join(CLASS_NAMES[name] for name in data['topClasses'])} {data['topClassCount']}건"
    topBin = "-" if not data["topBins"] else f"{'·'.join(BIN_NAMES.get(name, name) for name in data['topBins'])} {data['topBinCount']}건"
    classRows = []
    denominator = statistics["misclassificationCount"]
    for className, count in data["classCounts"].items():
        share = count / denominator * 100 if denominator else 0
        classRows.append((CLASS_NAMES[className], f"{count}건", f"{share:.1f}%"))
    binRows = [
        (
            BIN_NAMES.get(binName, binName),
            f"{counts['misclassification']}건",
            f"{counts['overflow']}건",
            f"{counts['total']}건",
        )
        for binName, counts in sorted(data["binCounts"].items())
    ] or [("-", "0건", "0건", "0건")]
    timelineRows = [
        (row["label"], f"{row['misclassification']}건", f"{row['overflow']}건", f"{row['total']}건")
        for row in data["timeline"]
    ]
    comparisonHtml = ""
    if previousData is not None:
        previousStatistics = previousData["statistics"]
        comparisonRows = [
            ("전체 이상 이벤트", previousStatistics["totalEventCount"], statistics["totalEventCount"], _changeText(statistics["totalEventCount"], previousStatistics["totalEventCount"])),
            ("오분류 이벤트", previousStatistics["misclassificationCount"], statistics["misclassificationCount"], _changeText(statistics["misclassificationCount"], previousStatistics["misclassificationCount"])),
            ("넘침 이벤트", previousStatistics["overflowCount"], statistics["overflowCount"], _changeText(statistics["overflowCount"], previousStatistics["overflowCount"])),
        ]
        comparisonRows.extend(
            (
                f"{CLASS_NAMES[name]} 오분류",
                previousData["classCounts"][name],
                data["classCounts"][name],
                _changeText(data["classCounts"][name], previousData["classCounts"][name]),
            )
            for name in CLASS_NAMES
        )
        allBins = sorted(set(data["binCounts"]) | set(previousData["binCounts"]))
        comparisonRows.extend(
            (
                BIN_NAMES.get(name, name),
                previousData["binCounts"].get(name, Counter())["total"],
                data["binCounts"].get(name, Counter())["total"],
                _changeText(data["binCounts"].get(name, Counter())["total"], previousData["binCounts"].get(name, Counter())["total"]),
            )
            for name in allBins
        )
        comparisonHtml = "<h2>전주 대비 증감</h2>" + _table(("항목", "이전 주", "이번 주", "변화"), comparisonRows)

    recentRows = []
    for event in data["recentEvents"]:
        local = parseTimestamp(event["timestamp"]).astimezone(period.startKst.tzinfo)
        confidence = "-" if event.get("confidenceScore") is None else f"{event['confidenceScore'] * 100:.1f}%"
        recentRows.append(
            (
                local.strftime("%m-%d %H:%M"),
                EVENT_NAMES[event["eventCategory"]],
                CLASS_NAMES.get(event.get("detectedClass"), "-"),
                BIN_NAMES.get(event.get("binType"), event.get("binId", "-")),
                confidence,
                ACTION_NAMES.get(event["actionTaken"], event["actionTaken"]),
            )
        )
    if not recentRows:
        recentRows.append(("-", "-", "-", "-", "-", "-"))
    periodText = f"{period.startKst:%Y-%m-%d %H:%M} ~ {period.endKst:%Y-%m-%d %H:%M} KST"
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><style>
body{{font-family:Arial,'Malgun Gothic',sans-serif;color:#253238;line-height:1.55;max-width:920px;margin:auto;padding:24px}}
h1{{color:#176b5b}} h2{{margin-top:28px;color:#245b50}} .summary{{background:#edf7f4;padding:16px;border-radius:8px}}
table{{border-collapse:collapse;width:100%;margin:10px 0}} th,td{{border:1px solid #d8e2df;padding:8px;text-align:left}} th{{background:#e4f1ed}}
.cards td{{width:33%}} .note{{font-size:12px;color:#667}} a{{color:#176b5b}}
</style></head><body>
<h1>SortMaster {reportName} 분리수거 현황 보고서</h1>
<p><strong>조회 기간:</strong> {html.escape(periodText)}<br><strong>생성 시각:</strong> {generated:%Y-%m-%d %H:%M:%S} KST<br><strong>시스템:</strong> SortMaster</p>
<div class="summary"><strong>자동 요약</strong><br>{html.escape(_summaryText(data))}</div>
<h2>핵심 요약</h2>
{_table(("전체 이상 이벤트", "오분류", "넘침"), [(f"{statistics['totalEventCount']}건", f"{statistics['misclassificationCount']}건", f"{statistics['overflowCount']}건")])}
<p>최다 오분류 클래스: <strong>{html.escape(topClass)}</strong><br>최다 발생 수거함: <strong>{html.escape(topBin)}</strong><br>오분류 이벤트 평균 AI 신뢰도: <strong>{average}</strong></p>
<h2>클래스별 오분류 현황</h2>{_table(("클래스", "발생 건수", "오분류 중 구성비"), classRows)}
<h2>수거함별 현황</h2>{_table(("수거함", "오분류", "넘침", "전체"), binRows)}
<h2>{'시간대별' if period.reportType == 'daily' else '요일별'} 현황</h2>{_table(("시간/요일", "오분류", "넘침", "전체"), timelineRows)}
{comparisonHtml}
<h2>최근 주요 이벤트</h2>{_table(("발생 시각", "이벤트 유형", "쓰레기 종류", "수거함", "신뢰도", "처리 결과"), recentRows)}
<p><a href="{html.escape(webBaseUrl + '/statistics')}">통계 페이지</a> · <a href="{html.escape(webBaseUrl + '/events')}">이전 기록 페이지</a></p>
<p class="note">평균 신뢰도는 저장된 오분류 이벤트의 모델 출력 평균이며 AI 모델 정확도가 아닙니다.<br>현재 경고 조치 결과는 시스템 처리 상태이며, 실제 전구와 경고음 장치의 작동 성공 여부는 아직 연동되지 않았습니다.<br>본 이메일은 RPA에 의해 자동 발송되었습니다.</p>
</body></html>"""


def buildCsv(events: list[dict[str, Any]], timezoneName: str) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    reportTimezone = ZoneInfo(timezoneName)
    for event in sorted(events, key=lambda item: parseTimestamp(item["timestamp"]), reverse=True):
        row = {field: event.get(field) for field in CSV_FIELDS}
        row["timestampKst"] = parseTimestamp(event["timestamp"]).astimezone(reportTimezone).isoformat()
        for optionalField in ("detectedClass", "confidenceScore", "imageFileId"):
            if row[optionalField] is None:
                row[optionalField] = ""
        writer.writerow(row)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def buildExecutionKey(period: ReportPeriod, recipientGroup: str) -> str:
    return f"{period.reportType}:{period.fileLabel}:{recipientGroup}"


class StateStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.statePath = directory / "sentReports.json"
        self.lockPath = directory / "reportAutomation.lock"

    @contextmanager
    def lock(self) -> Iterator[None]:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._removeStaleLock()
        try:
            descriptor = os.open(self.lockPath, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            raise LockUnavailableError("다른 보고서 프로세스가 실행 중입니다.") from error
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as lockFile:
                json.dump({"pid": os.getpid(), "createdAt": datetime.now(timezone.utc).isoformat()}, lockFile)
            yield
        finally:
            try:
                self.lockPath.unlink()
            except FileNotFoundError:
                pass

    def _removeStaleLock(self) -> None:
        if not self.lockPath.exists():
            return
        try:
            lockData = json.loads(self.lockPath.read_text(encoding="utf-8"))
            createdAt = parseTimestamp(lockData["createdAt"])
        except (OSError, KeyError, TypeError, json.JSONDecodeError, ApiResponseError):
            return
        if datetime.now(timezone.utc) - createdAt <= timedelta(hours=6):
            return
        try:
            self.lockPath.unlink()
        except FileNotFoundError:
            pass

    def load(self) -> dict[str, Any]:
        if not self.statePath.exists():
            return {"reports": {}}
        try:
            data = json.loads(self.statePath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ReportAutomationError("발송 이력 파일을 읽을 수 없습니다.") from error
        if not isinstance(data, dict) or not isinstance(data.get("reports"), dict):
            raise ReportAutomationError("발송 이력 파일 형식이 잘못되었습니다.")
        return data

    def save(self, state: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.statePath.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.statePath)

    def deliveredRecipients(self, executionKey: str) -> set[str]:
        record = self.load()["reports"].get(executionKey, {})
        return set(record.get("deliveredRecipients", []))

    def recordDelivery(self, executionKey: str, recipients: set[str], complete: bool) -> None:
        state = self.load()
        record = state["reports"].setdefault(executionKey, {})
        delivered = set(record.get("deliveredRecipients", [])) | recipients
        record.update(
            {
                "status": "sent" if complete else "partial",
                "deliveredRecipients": sorted(delivered),
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.save(state)


def _retry(
    operation: Callable[[], Any],
    retryDelays: tuple[float, ...],
    logger: logging.Logger,
    operationName: str,
    retryableErrors: tuple[type[BaseException], ...],
) -> Any:
    attempts = len(retryDelays) + 1
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except retryableErrors:
            if attempt == attempts:
                raise
            delay = retryDelays[attempt - 1]
            logger.warning("operation=%s attempt=%d/%d status=RETRY delaySeconds=%s", operationName, attempt, attempts, delay)
            time.sleep(delay)


def createEmail(
    subject: str,
    htmlBody: str,
    csvBytes: bytes,
    csvFilename: str,
    sender: str,
    recipients: tuple[str, ...],
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content("SortMaster 자동 보고서입니다. HTML을 지원하는 메일에서 확인해 주세요.")
    message.add_alternative(htmlBody, subtype="html")
    message.add_attachment(csvBytes, maintype="text", subtype="csv", filename=csvFilename)
    return message


def sendEmail(settings: Settings, message: EmailMessage, recipients: tuple[str, ...]) -> set[str]:
    try:
        with smtplib.SMTP(settings.smtpHost, settings.smtpPort, timeout=settings.requestTimeoutSeconds) as smtp:
            smtp.ehlo()
            if settings.smtpUseTls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if settings.smtpUser:
                smtp.login(settings.smtpUser, settings.smtpPassword)
            refused = smtp.send_message(message, from_addr=settings.sender, to_addrs=recipients)
    except smtplib.SMTPAuthenticationError as error:
        raise SmtpAuthenticationError("SMTP 인증에 실패했습니다.") from error
    accepted = set(recipients) - set(refused)
    if not accepted:
        raise smtplib.SMTPRecipientsRefused(refused)
    return accepted


def _subject(period: ReportPeriod, force: bool) -> str:
    reportName = "일일" if period.reportType == "daily" else "주간"
    resend = "[재발송] " if force else ""
    return f"{resend}[SortMaster] {period.dateLabel} {reportName} 분리수거 현황 보고서"


def runReport(
    reportType: str,
    settings: Settings,
    force: bool = False,
    dryRun: bool = False,
    targetDate: date | None = None,
    now: datetime | None = None,
    apiClient: ApiClient | None = None,
    emailSender: Callable[[Settings, EmailMessage, tuple[str, ...]], set[str]] = sendEmail,
) -> dict[str, Any]:
    logger = logging.getLogger("reportAutomation")
    if reportType == "weekly" and targetDate is not None and targetDate.weekday() != 0:
        raise ValueError("weekly --date는 월요일이어야 합니다.")
    period = calculatePeriod(reportType, now, settings.timezoneName, targetDate)
    executionKey = buildExecutionKey(period, settings.recipientGroup)
    store = StateStore(settings.stateDirectory)
    logger.info("report=%s period=%s status=STARTED", reportType, period.fileLabel)
    with store.lock():
        delivered = store.deliveredRecipients(executionKey)
        if delivered and not force and delivered.issuperset(settings.recipients):
            raise DuplicateReportError(f"이미 발송된 보고서입니다: {executionKey}")
        client = apiClient or ApiClient(settings.apiBaseUrl, settings.requestTimeoutSeconds)
        statistics, events = _retry(
            lambda: client.getReportData(period),
            settings.retryDelays,
            logger,
            "api-current",
            (ConnectionError,),
        )
        validateData(statistics, events, period)
        data = aggregateData(statistics, events, period)
        previousData = None
        if reportType == "weekly":
            comparisonPeriod = previousPeriod(period)
            previousStatistics, previousEvents = _retry(
                lambda: client.getReportData(comparisonPeriod),
                settings.retryDelays,
                logger,
                "api-previous",
                (ConnectionError,),
            )
            validateData(previousStatistics, previousEvents, comparisonPeriod)
            previousData = aggregateData(previousStatistics, previousEvents, comparisonPeriod)
        logger.info("statistics=%d events=%d status=VALIDATED", statistics["totalEventCount"], len(events))
        htmlBody = buildHtml(data, period, settings.webBaseUrl, previousData)
        csvBytes = buildCsv(events, settings.timezoneName)
        csvFilename = f"sortmaster_{reportType}_{period.fileLabel}.csv"

        if dryRun:
            settings.outputDirectory.mkdir(parents=True, exist_ok=True)
            htmlPath = settings.outputDirectory / f"sortmaster_{reportType}_{period.fileLabel}.html"
            csvPath = settings.outputDirectory / csvFilename
            htmlPath.write_text(htmlBody, encoding="utf-8")
            csvPath.write_bytes(csvBytes)
            logger.info("status=DRY_RUN html=%s csv=%s", htmlPath, csvPath)
            return {"status": "dryRun", "htmlPath": str(htmlPath), "csvPath": str(csvPath), "period": period}

        pending = settings.recipients if force else tuple(address for address in settings.recipients if address not in delivered)
        if not pending:
            raise DuplicateReportError(f"발송할 신규 수신자가 없습니다: {executionKey}")
        message = createEmail(_subject(period, force), htmlBody, csvBytes, csvFilename, settings.sender, pending)

        remaining = set(pending)
        lastError: BaseException | None = None
        attempts = len(settings.retryDelays) + 1
        for attempt in range(1, attempts + 1):
            try:
                accepted = emailSender(settings, message, tuple(sorted(remaining)))
                delivered |= accepted
                remaining -= accepted
                store.recordDelivery(executionKey, delivered, not remaining)
                if not remaining:
                    logger.info("recipients=%d status=SENT", len(delivered))
                    return {"status": "sent", "recipients": sorted(delivered), "period": period}
                lastError = smtplib.SMTPRecipientsRefused({address: (450, b"temporarily refused") for address in remaining})
            except SmtpAuthenticationError:
                raise
            except (smtplib.SMTPException, OSError) as error:
                lastError = error
            if attempt < attempts:
                delay = settings.retryDelays[attempt - 1]
                logger.warning(
                    "operation=smtp attempt=%d/%d status=RETRY delaySeconds=%s "
                    "pendingRecipients=%d errorType=%s",
                    attempt,
                    attempts,
                    delay,
                    len(remaining),
                    type(lastError).__name__,
                )
                time.sleep(delay)
        assert lastError is not None
        raise lastError


def configureLogging(stateDirectory: Path) -> None:
    stateDirectory.mkdir(parents=True, exist_ok=True)
    logFormat = "%(asctime)s %(levelname)s %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        handlers.append(logging.FileHandler(stateDirectory / "reportAutomation.log", encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO, format=logFormat, handlers=handlers)


def _loadDotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    repositoryRoot = Path(__file__).resolve().parents[2]
    load_dotenv(repositoryRoot / ".env")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SortMaster 일일/주간 이메일 보고서 자동화")
    parser.add_argument("reportType", choices=("daily", "weekly"))
    parser.add_argument("--force", action="store_true", help="이미 발송된 보고서도 [재발송] 제목으로 전송")
    parser.add_argument("--dry-run", action="store_true", help="이메일 대신 HTML/CSV 미리보기 파일 생성")
    parser.add_argument("--date", help="일일 대상일 또는 주간 시작 월요일(YYYY-MM-DD)")
    args = parser.parse_args(argv)
    _loadDotenv()
    try:
        targetDate = date.fromisoformat(args.date) if args.date else None
        settings = Settings.fromEnvironment(requireEmail=not args.dry_run)
        configureLogging(settings.stateDirectory)
        if not settings.enabled:
            logging.getLogger("reportAutomation").info("status=DISABLED")
            return 0
        runReport(args.reportType, settings, args.force, args.dry_run, targetDate)
        return 0
    except (ReportAutomationError, ValueError, HTTPError, smtplib.SMTPException, OSError) as error:
        logging.getLogger("reportAutomation").error("status=FAILED errorType=%s message=%s", type(error).__name__, error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
