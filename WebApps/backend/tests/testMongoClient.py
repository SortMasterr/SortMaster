import unittest
from unittest.mock import AsyncMock, patch

from repositories import mongoClient


class FakeClient:
    def __init__(self):
        self.database = object()
        self.closed = False

    def __getitem__(self, _databaseName):
        return self.database

    def close(self):
        self.closed = True


class MongoClientLifecycleTest(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        mongoClient.closeMongoClient()

    async def testCloseIsIdempotentAndResetsClient(self):
        fakeClient = FakeClient()

        with patch.object(
            mongoClient,
            "AsyncIOMotorClient",
            return_value=fakeClient,
        ) as createClient:
            database = mongoClient.getMongoDb()

        self.assertIs(database, fakeClient.database)
        self.assertEqual(
            5000,
            createClient.call_args.kwargs[
                "serverSelectionTimeoutMS"
            ],
        )

        mongoClient.closeMongoClient()
        mongoClient.closeMongoClient()

        self.assertTrue(fakeClient.closed)
        self.assertIsNone(mongoClient._client)
        self.assertIsNone(mongoClient._clientLoop)

    async def testPingUsesConfiguredDatabase(self):
        database = AsyncMock()

        with patch.object(
            mongoClient,
            "getMongoDb",
            return_value=database,
        ):
            await mongoClient.pingMongo()

        database.command.assert_awaited_once_with("ping")


if __name__ == "__main__":
    unittest.main()
