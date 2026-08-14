"""
로컬 Docker MongoDB(events 컬렉션)에 대시보드/통계 테스트용 더미 이벤트 20건 삽입.

실제 백엔드(eventService.createEvent)는 5초 Cooldown + "지금 시각"만 허용해서
API를 통해선 과거 날짜로 퍼진 테스트 데이터를 못 만듦 — 그래서 이 스크립트는
eventRepository와 같은 events 컬렉션에 pymongo로 직접 insert함(schemas/event.py의
현재 필드 구조 기준, ERD.md에 새로 확정된 binId/detectionId 등은 아직 코드 미반영이라 제외).

eventId는 전부 "seed-"로 시작 — 나중에 지우고 싶으면:
    db.events.deleteMany({eventId: {$regex: "^seed-"}})

실행:
    python debug/db/seedTestEvents.py
"""
import os
import random
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
from uuid import uuid4

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
events = client[mongoDbName]["events"]

# ELEV-TOP: 쓰레기 종류 분류+쓰레기통 감지+투척 감지 3기능 모델 → misclassification 전담
# ELEV-SIDE: 쓰레기통 넘침 여부만 판정 → overflow 전담(architecture.md 참고)
# REST-4F-01은 아직 설치 확정 전(고도화 단계 스트레치 목표)이라 시드 데이터에서 제외
#
detectedClasses = ["general", "paper", "plastic", "can", "coffeeCup"]
actionTakens = ["lightAndSound", "none"]

now = datetime.now(timezone.utc)
documents = []

# misclassification 14건 — 실제 서비스 로직(eventService.createEvent)은
# isMisclassified=False면 이벤트 자체를 저장 안 하므로, 실제 운영 데이터와
# 맞추기 위해 전부 True로 생성
for i in range(14):
    documents.append(
        {
            "eventId": f"seed-misc-{i:02d}",
            "timestamp": now - timedelta(
                hours=random.randint(0, 24 * 7),
                minutes=random.randint(0, 59),
            ),
            "cameraId": "ELEV-TOP",
            "eventCategory": "misclassification",
            "detectedClass": random.choice(detectedClasses),
            "isMisclassified": True,
            "confidenceScore": round(random.uniform(0.70, 0.99), 2),
            "actionTaken": random.choice(actionTakens),
            "imageFileId": None,
            "notes": None,
        }
    )

# overflow 6건
for i in range(6):
    documents.append(
        {
            "eventId": f"seed-overflow-{i:02d}",
            "timestamp": now - timedelta(
                hours=random.randint(0, 24 * 7),
                minutes=random.randint(0, 59),
            ),
            "cameraId": "ELEV-SIDE",
            "eventCategory": "overflow",
            "detectedClass": None,
            "isMisclassified": None,
            "confidenceScore": None,
            "actionTaken": random.choice(actionTakens),
            "imageFileId": None,
            "notes": None,
        }
    )

result = events.insert_many(documents)
print(f"삽입 완료: {len(result.inserted_ids)}건")
