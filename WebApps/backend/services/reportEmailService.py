import sys
from pathlib import Path

from dotenv import load_dotenv

from schemas.report import (
    ReportEmailSettingsRequest,
    ReportEmailSettingsResponse,
)
from services.errors import ReportEmailSettingsError


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
    ConfigurationError,
    RecipientSettingsStore,
    Settings,
)


class ReportEmailService:
    def getSettings(self) -> ReportEmailSettingsResponse:
        try:
            store = self._getStore()
            recipient = store.loadRecipient()
        except ConfigurationError as error:
            raise ReportEmailSettingsError(str(error)) from error
        return ReportEmailSettingsResponse(
            configured=recipient is not None,
            recipient=recipient,
            message=(
                "자동 보고서 수신 이메일이 설정되어 있습니다."
                if recipient
                else "자동 보고서 수신 이메일을 설정해 주세요."
            ),
        )

    def saveSettings(
        self,
        request: ReportEmailSettingsRequest,
    ) -> ReportEmailSettingsResponse:
        try:
            store = self._getStore()
            if request.recipient is None:
                store.clearRecipient()
                recipient = None
            else:
                recipient = store.saveRecipient(request.recipient)
        except ConfigurationError as error:
            raise ReportEmailSettingsError(str(error)) from error
        return ReportEmailSettingsResponse(
            configured=recipient is not None,
            recipient=recipient,
            message=(
                "자동 보고서 수신 이메일을 저장했습니다."
                if recipient
                else "자동 보고서 이메일 수신을 해제했습니다."
            ),
        )

    @staticmethod
    def _getStore() -> RecipientSettingsStore:
        load_dotenv(repositoryRoot / ".env")
        settings = Settings.fromEnvironment(
            requireEmail=False,
            requireRecipients=False,
        )
        return RecipientSettingsStore(settings.stateDirectory)


reportEmailService = ReportEmailService()
