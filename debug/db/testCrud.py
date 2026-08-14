"""
로컬 Docker MongoDB CRUD 테스트 (호스트 포트 27020).
"""
import os
from datetime import datetime, timezone
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

mongoHost = os.getenv("MONGO_HOST", "localhost")
mongoPort = os.getenv("DB_PORT", "27020")
mongoUser = os.getenv("DB_USER")
mongoPassword = os.getenv("DB_PASSWORD")
mongoDbName = os.getenv("DB_NAME", "sortMaster")

if mongoUser and mongoPassword:
    auth = f"{quote_plus(mongoUser)}:{quote_plus(mongoPassword)}@"
else:
    auth = ""

mongoUri = (
    f"mongodb://{auth}{mongoHost}:{mongoPort}/"
    f"?appName=sortMasterDB&authSource={mongoDbName}"
)

client = MongoClient(mongoUri, server_api=ServerApi("1"))
db = client[mongoDbName]  # DB 이름은 .env의 DB_NAME(없으면 자동 생성)
events = db["events"]  # 컬렉션 이름 (없으면 자동 생성, 실제 백엔드가 쓰는 것과 동일한 컬렉션)

# CREATE
doc = {
    "eventId": "test-0001",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "cameraId": "ELEV-TOP",
    "detectedClass": "plastic",
    "isMisclassified": True,
    "confidenceScore": 0.87,
    "actionTaken": "lightAndSound",
}
result = events.insert_one(doc)
print("생성됨:", result.inserted_id)

# READ
found = events.find_one({"eventId": "test-0001"})
print("조회됨:", found)

# UPDATE
events.update_one({"eventId": "test-0001"}, {"$set": {"notes": "테스트 수정"}})
print("수정 후:", events.find_one({"eventId": "test-0001"}))

# DELETE
events.delete_one({"eventId": "test-0001"})
print("삭제 후:", events.find_one({"eventId": "test-0001"}))
