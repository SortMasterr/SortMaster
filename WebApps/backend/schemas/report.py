import re

from pydantic import BaseModel, Field, field_validator


class ReportEmailSettingsRequest(BaseModel):
    recipient: str = Field(min_length=3, max_length=254)

    @field_validator("recipient")
    @classmethod
    def validateRecipient(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("올바른 이메일 주소를 입력해 주세요.")
        return normalized


class ReportEmailSettingsResponse(BaseModel):
    configured: bool
    recipient: str | None
    message: str
