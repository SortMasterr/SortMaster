import tempfile
import unittest
from pathlib import Path

from services.reportEmailService import _findRepositoryRoot


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


if __name__ == "__main__":
    unittest.main()
