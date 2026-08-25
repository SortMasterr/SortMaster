import re
from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class ReportType(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"


class ReportEmailRequest(BaseModel):
    recipient: str = Field(min_length=3, max_length=254)
    reportType: ReportType = ReportType.DAILY
    targetDate: date | None = None

    @field_validator("recipient")
    @classmethod
    def validateRecipient(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("올바른 이메일 주소를 입력해 주세요.")
        return normalized


class ReportEmailResponse(BaseModel):
    status: str
    reportType: ReportType
    period: str
    recipient: str
    message: str
