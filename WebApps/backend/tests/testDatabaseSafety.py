import sys
import unittest
from pathlib import Path


debugDbDirectory = (
    Path(__file__).resolve().parents[3]
    / "debug"
    / "db"
)
sys.path.insert(0, str(debugDbDirectory))

from databaseSafety import requireLocalTestDatabase
from seedTestEvents import buildDocuments
from schemas.event import Event


class DatabaseSafetyTest(unittest.TestCase):
    def testAllowsOnlyLocalNamedTestDatabase(self):
        requireLocalTestDatabase(
            "localhost",
            "sortMasterTest",
        )
        requireLocalTestDatabase(
            "127.0.0.1",
            "sortMasterTest",
        )

    def testRejectsSharedHost(self):
        with self.assertRaises(RuntimeError):
            requireLocalTestDatabase(
                "192.168.0.40",
                "sortMaster",
            )

    def testRejectsProductionNameOnLocalhost(self):
        with self.assertRaises(RuntimeError):
            requireLocalTestDatabase(
                "localhost",
                "sortMaster",
            )

    def testSeedDocumentsMatchCurrentEventSchema(self):
        documents = buildDocuments()

        self.assertEqual(20, len(documents))

        for document in documents:
            Event.model_validate(document)


if __name__ == "__main__":
    unittest.main()
