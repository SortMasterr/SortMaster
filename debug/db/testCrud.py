"""Local sortMasterTest MongoDB CRUD smoke check."""

import os
from datetime import datetime, timezone
from urllib.parse import quote_plus
from uuid import uuid4

from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

try:
    from .databaseSafety import requireLocalTestDatabase
except ImportError:
    from databaseSafety import requireLocalTestDatabase


def main() -> None:
    load_dotenv()

    mongoHost = os.getenv("MONGO_HOST", "localhost")
    mongoPort = os.getenv("DB_PORT", "27020")
    mongoUser = os.getenv("DB_USER")
    mongoPassword = os.getenv("DB_PASSWORD")
    mongoDbName = os.getenv("DB_NAME", "sortMasterTest")

    requireLocalTestDatabase(mongoHost, mongoDbName)

    if mongoUser and mongoPassword:
        auth = (
            f"{quote_plus(mongoUser)}:"
            f"{quote_plus(mongoPassword)}@"
        )
    else:
        auth = ""

    mongoUri = (
        f"mongodb://{auth}{mongoHost}:{mongoPort}/"
        f"?appName=sortMasterDB&authSource={mongoDbName}"
    )

    client = MongoClient(
        mongoUri,
        server_api=ServerApi("1"),
    )
    events = client[mongoDbName]["events"]
    testEventId = f"test-{uuid4()}"

    document = {
        "eventId": testEventId,
        "timestamp": datetime.now(timezone.utc),
        "cameraId": "ELEV-TOP",
        "eventCategory": "misclassification",
        "detectionId": f"test-detection-{uuid4()}",
        "trackingId": 1,
        "detectedClass": "plasticCan",
        "binId": "BIN-PAPER",
        "binType": "paper",
        "isMisclassified": True,
        "confidenceScore": 0.87,
        "actionTaken": "lightAndSound",
        "imageFileId": None,
        "overflowDuration": None,
        "overflowThreshold": None,
        "modelVersion": "crud-test-v1",
        "notes": None,
    }

    try:
        result = events.insert_one(document)
        print("생성됨:", result.inserted_id)

        print(
            "조회됨:",
            events.find_one({"eventId": testEventId}),
        )

        events.update_one(
            {"eventId": testEventId},
            {"$set": {"notes": "테스트 수정"}},
        )
        print(
            "수정 후:",
            events.find_one({"eventId": testEventId}),
        )

        events.delete_one({"eventId": testEventId})
        print(
            "삭제 후:",
            events.find_one({"eventId": testEventId}),
        )
    finally:
        events.delete_one({"eventId": testEventId})
        client.close()


if __name__ == "__main__":
    main()
