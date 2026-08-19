"""Insert 20 current-schema dashboard events into local sortMasterTest.

The normal API creates events at the current time and applies cooldown, so this
script inserts historical test fixtures directly. It only runs against a
loopback MongoDB with DB_NAME=sortMasterTest.
"""

import os
import random
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
from uuid import uuid4

from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

try:
    from .databaseSafety import requireLocalTestDatabase
except ImportError:
    from databaseSafety import requireLocalTestDatabase


detectedClasses = [
    "general",
    "paper",
    "plastic",
    "can",
    "coffeeCup",
]
actionTakens = ["lightAndSound", "none"]
expectedBinTypeByClass = {
    "general": "general",
    "paper": "paper",
    "plastic": "plasticCan",
    "can": "plasticCan",
    "coffeeCup": "coffeeCup",
}
binIdByType = {
    "general": "BIN-GENERAL",
    "paper": "BIN-PAPER",
    "plasticCan": "BIN-PLASTIC-CAN",
    "coffeeCup": "BIN-COFFEE-CUP",
}


def buildDocuments(
    currentTime: datetime | None = None,
) -> list[dict]:
    now = currentTime or datetime.now(timezone.utc)
    documents = []
    binTypes = list(binIdByType)

    for trackingId in range(14):
        detectedClass = random.choice(detectedClasses)
        expectedBinType = expectedBinTypeByClass[
            detectedClass
        ]
        wrongBinType = random.choice(
            [
                binType
                for binType in binTypes
                if binType != expectedBinType
            ]
        )

        documents.append(
            {
                "eventId": f"seed-misc-{uuid4()}",
                "timestamp": now
                - timedelta(
                    hours=random.randint(0, 24 * 7),
                    minutes=random.randint(0, 59),
                ),
                "cameraId": "ELEV-TOP",
                "eventCategory": "misclassification",
                "detectionId": (
                    f"seed-detection-misc-{uuid4()}"
                ),
                "trackingId": trackingId,
                "detectedClass": detectedClass,
                "binId": binIdByType[wrongBinType],
                "binType": wrongBinType,
                "isMisclassified": True,
                "confidenceScore": round(
                    random.uniform(0.70, 0.99),
                    2,
                ),
                "actionTaken": random.choice(actionTakens),
                "imageFileId": None,
                "overflowDuration": None,
                "overflowThreshold": None,
                "modelVersion": "seed-test-v1",
                "notes": None,
            }
        )

    for _index in range(6):
        documents.append(
            {
                "eventId": f"seed-overflow-{uuid4()}",
                "timestamp": now
                - timedelta(
                    hours=random.randint(0, 24 * 7),
                    minutes=random.randint(0, 59),
                ),
                "cameraId": "ELEV-SIDE",
                "eventCategory": "overflow",
                "detectionId": (
                    f"seed-detection-overflow-{uuid4()}"
                ),
                "trackingId": None,
                "detectedClass": None,
                "binId": "BIN-GENERAL",
                "binType": "general",
                "isMisclassified": None,
                "confidenceScore": None,
                "actionTaken": random.choice(actionTakens),
                "imageFileId": None,
                "overflowDuration": 5.0,
                "overflowThreshold": 5.0,
                "modelVersion": "seed-test-v1",
                "notes": None,
            }
        )

    return documents


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

    try:
        events = client[mongoDbName]["events"]
        result = events.insert_many(buildDocuments())
        print(f"삽입 완료: {len(result.inserted_ids)}건")
    finally:
        client.close()


if __name__ == "__main__":
    main()
