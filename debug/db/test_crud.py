from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from urllib.parse import quote_plus
from dotenv import load_dotenv
from datetime import datetime, timezone
import os

load_dotenv()
username = quote_plus(os.getenv("MONGO_USER"))
password = quote_plus(os.getenv("MONGO_PASSWORD"))
host = os.getenv("MONGO_HOST")
MONGO_URI = f"mongodb+srv://{username}:{password}@{host}/?appName=sortMasterDB"

client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
db = client["cctv_project"]          # DB 이름 (없으면 자동 생성)
events = db["events"]                # 컬렉션 이름 (없으면 자동 생성)

# CREATE
doc = {
    "eventId": "test-0001",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "cameraId": "ELEV-01",
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