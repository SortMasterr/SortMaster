import asyncio
import hashlib
import sys
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

from schemas.report import ReportEmailRequest, ReportEmailResponse


def _findRepositoryRoot(servicePath: Path) -> Path:
    for parent in servicePath.resolve().parents:
        reportModule = (
            parent
            / "RPAs"
            / "reportAutomation"
            / "reportAutomation.py"
        )
        if reportModule.is_file():
            return parent

    raise RuntimeError(
        "RPAs/reportAutomation/reportAutomation.py를 찾을 수 없습니다."
    )


repositoryRoot = _findRepositoryRoot(Path(__file__))
if str(repositoryRoot) not in sys.path:
    sys.path.insert(0, str(repositoryRoot))

from RPAs.reportAutomation.reportAutomation import (  # noqa: E402
    ApiResponseError,
    ConfigurationError,
    DataMismatchError,
    DuplicateReportError,
    LockUnavailableError,
    Settings,
    SmtpAuthenticationError,
    runReport,
)


class ReportEmailService:
    async def sendReport(
        self,
        request: ReportEmailRequest,
    ) -> ReportEmailResponse:
        return await asyncio.to_thread(
            self._sendReport,
            request,
        )

    def _sendReport(
        self,
        request: ReportEmailRequest,
    ) -> ReportEmailResponse:
        load_dotenv(repositoryRoot / ".env")
        settings = Settings.fromEnvironment(
            requireEmail=True,
            requireRecipients=False,
        )
        if not settings.enabled:
            raise ConfigurationError("이메일 보고서 발송 기능이 비활성화되어 있습니다.")

        recipientKey = hashlib.sha256(
            request.recipient.encode("utf-8")
        ).hexdigest()[:16]
        manualSettings = replace(
            settings,
            recipients=(request.recipient,),
            recipientGroup=f"manual-{recipientKey}",
            retryDelays=(1.0, 5.0),
        )
        result = runReport(
            request.reportType.value,
            manualSettings,
            targetDate=request.targetDate,
        )
        period = result["period"]
        return ReportEmailResponse(
            status=result["status"],
            reportType=request.reportType,
            period=period.dateLabel,
            recipient=request.recipient,
            message="보고서 이메일을 발송했습니다.",
        )


reportEmailService = ReportEmailService()
