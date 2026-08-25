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


if __name__ == "__main__":
    unittest.main()
