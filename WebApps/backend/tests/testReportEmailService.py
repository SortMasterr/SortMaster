import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from schemas.report import ReportEmailSettingsRequest
from services.reportEmailService import (
    _findRepositoryRoot,
    reportEmailService,
)


class ReportEmailServicePathTest(unittest.TestCase):
    def testFindsRepositoryRootInShallowContainerLayout(self):
        with tempfile.TemporaryDirectory() as temporaryDirectory:
            repositoryRoot = Path(temporaryDirectory)
            reportModule = (
                repositoryRoot
                / "RPAs"
                / "reportAutomation"
                / "reportAutomation.py"
            )
            reportModule.parent.mkdir(parents=True)
            reportModule.touch()
            servicePath = (
                repositoryRoot
                / "services"
                / "reportEmailService.py"
            )

            result = _findRepositoryRoot(servicePath)

        self.assertEqual(repositoryRoot.resolve(), result)

    def testRaisesWhenReportModuleIsMissing(self):
        with tempfile.TemporaryDirectory() as temporaryDirectory:
            servicePath = (
                Path(temporaryDirectory)
                / "services"
                / "reportEmailService.py"
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "RPAs/reportAutomation/reportAutomation.py",
            ):
                _findRepositoryRoot(servicePath)

    def testSavesAndLoadsAutomaticReportRecipient(self):
        with tempfile.TemporaryDirectory() as temporaryDirectory:
            with patch.dict(
                os.environ,
                {"RPA_STATE_DIRECTORY": temporaryDirectory},
            ):
                saved = reportEmailService.saveSettings(
                    ReportEmailSettingsRequest(
                        recipient="Manager@Example.com"
                    )
                )
                loaded = reportEmailService.getSettings()

        self.assertTrue(saved.configured)
        self.assertEqual("manager@example.com", saved.recipient)
        self.assertEqual(saved.recipient, loaded.recipient)

    def testClearsAutomaticReportRecipient(self):
        with tempfile.TemporaryDirectory() as temporaryDirectory:
            with patch.dict(
                os.environ,
                {
                    "RPA_STATE_DIRECTORY": temporaryDirectory,
                    "RPA_REPORT_RECIPIENTS": "fallback@example.com",
                },
            ):
                reportEmailService.saveSettings(
                    ReportEmailSettingsRequest(
                        recipient="manager@example.com"
                    )
                )
                cleared = reportEmailService.saveSettings(
                    ReportEmailSettingsRequest(recipient=None)
                )
                loaded = reportEmailService.getSettings()

        self.assertFalse(cleared.configured)
        self.assertIsNone(cleared.recipient)
        self.assertEqual(
            "자동 보고서 이메일 수신을 해제했습니다.",
            cleared.message,
        )
        self.assertFalse(loaded.configured)
        self.assertIsNone(loaded.recipient)


if __name__ == "__main__":
    unittest.main()
