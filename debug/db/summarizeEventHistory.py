"""
발표 슬라이드용 실측 3종 세트를 한 번에 뽑는 읽기 전용 스크립트.

- 실제 관측 기간: events 컬렉션 timestamp 최초~최신
- 탐지된 오분류: events 컬렉션 isMisclassified == true 건수
- 기록된 방문: visitClips 컬렉션 전체 문서 수

testDbConnection.py/checkVisitClips.py와 동일한 URI 조립 규칙(.env의 MONGO_HOST/
DB_PORT/DB_USER/DB_PASSWORD/DB_NAME)을 쓰며, 조회만 하고 아무것도 쓰지 않는다.
로컬/팀 배포 서버 어느 쪽 .env로도 실행 가능(checkVisitClips.py와 동일 성격).
"""
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

mongoHost = os.getenv("MONGO_HOST", "localhost")
mongoPort = os.getenv("DB_PORT", "27020")
mongoUser = os.getenv("DB_USER")
mongoPassword = os.getenv("DB_PASSWORD")
mongoDbName = os.getenv("DB_NAME", "sortMaster")

auth = f"{quote_plus(mongoUser)}:{quote_plus(mongoPassword)}@" if mongoUser and mongoPassword else ""
mongoUri = (
    f"mongodb://{auth}{mongoHost}:{mongoPort}/"
    f"?appName=summarizeEventHistory&authSource={mongoDbName}"
)

print(f"접속 대상: MONGO_HOST={mongoHost} DB_NAME={mongoDbName}")

client = MongoClient(mongoUri, serverSelectionTimeoutMS=5000)
db = client[mongoDbName]

earliest = db.events.find_one({}, {"_id": 0, "timestamp": 1}, sort=[("timestamp", 1)])
latest = db.events.find_one({}, {"_id": 0, "timestamp": 1}, sort=[("timestamp", -1)])
misclassifiedCount = db.events.count_documents({"isMisclassified": True})
totalEventCount = db.events.count_documents({})
visitClipCount = db.visitClips.count_documents({})

print("\n=== events ===")
if earliest and latest:
    earliestTs = earliest["timestamp"]
    latestTs = latest["timestamp"]
    observedDays = (latestTs - earliestTs).days + 1
    print(f"최초 timestamp: {earliestTs}")
    print(f"최신 timestamp: {latestTs}")
    print(f"관측 기간(일, 양끝 포함): {observedDays}")
else:
    print("events 문서가 없음 - 관측 기간 계산 불가")

print(f"전체 events 문서 수: {totalEventCount}")
print(f"isMisclassified=true 건수: {misclassifiedCount}")

print("\n=== visitClips ===")
print(f"전체 visitClips 문서 수: {visitClipCount}")

print("\n=== 슬라이드용 요약 ===")
if earliest and latest:
    print(f"?? 일 -> {observedDays}일")
print(f"?? 건 -> {misclassifiedCount}건")
print(f"?? 회 -> {visitClipCount}회")

client.close()
