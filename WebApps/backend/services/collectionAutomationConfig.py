import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


servicePath = Path(__file__).resolve()
for parent in servicePath.parents:
    if (parent / "RPAs" / "reportAutomation" / "reportAutomation.py").is_file():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        break

from RPAs.reportAutomation.reportAutomation import (
    ConfigurationError,
    normalizeEmailAddress,
)


def loadProjectDotenv() -> None:
    servicePath = Path(__file__).resolve()
    for parent in servicePath.parents:
        candidate = parent / ".env"
        if candidate.is_file():
            load_dotenv(candidate)
            return


def parseBool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"boolean 환경변수 값이 잘못되었습니다: {value!r}")


@dataclass(frozen=True)
class CollectionAutomationConfig:
    enabled: bool
    assigneeEmail: str | None
    managerEmail: str | None
    reminderMinutes: float
    escalationMinutes: float
    pollSeconds: float
    retrySeconds: float

    @classmethod
    def fromEnvironment(cls) -> "CollectionAutomationConfig":
        loadProjectDotenv()
        try:
            reminderMinutes = float(os.getenv("RPA_COLLECTION_REMINDER_MINUTES", "10"))
            escalationMinutes = float(os.getenv("RPA_COLLECTION_ESCALATION_MINUTES", "20"))
            pollSeconds = float(os.getenv("RPA_COLLECTION_POLL_SECONDS", "30"))
            retrySeconds = float(os.getenv("RPA_COLLECTION_RETRY_SECONDS", "60"))
        except ValueError as error:
            raise ConfigurationError("수거 자동화 시간 설정은 숫자여야 합니다.") from error
        if min(reminderMinutes, escalationMinutes, pollSeconds, retrySeconds) <= 0:
            raise ConfigurationError("수거 자동화 시간 설정은 0보다 커야 합니다.")
        if escalationMinutes <= reminderMinutes:
            raise ConfigurationError(
                "관리자 에스컬레이션 시간은 담당자 재알림 시간보다 커야 합니다."
            )

        def optionalEmail(name: str) -> str | None:
            value = os.getenv(name, "").strip()
            return normalizeEmailAddress(value) if value else None

        return cls(
            enabled=parseBool(os.getenv("RPA_COLLECTION_ENABLED", "false")),
            assigneeEmail=optionalEmail("RPA_COLLECTION_ASSIGNEE_EMAIL"),
            managerEmail=optionalEmail("RPA_COLLECTION_MANAGER_EMAIL"),
            reminderMinutes=reminderMinutes,
            escalationMinutes=escalationMinutes,
            pollSeconds=pollSeconds,
            retrySeconds=retrySeconds,
        )
