"""
visitClips 컬렉션이 실제로 쌓이고 있는지 확인하는 읽기 전용 스크립트.

presenceGateService가 사람 감지 방문마다 무조건 저장하는 컬렉션이라(GPU 판정 결과와
무관, .agentfiles/architecture.md의 "재학습용 미확정 방문 캡처" 참고), 배포 직후
실제로 방문 하나를 만들어보고 이 스크립트로 문서가 생겼는지 확인하면 된다.

testDbConnection.py와 동일한 URI 조립 규칙(.env의 MONGO_HOST/DB_PORT/DB_USER/
DB_PASSWORD/DB_NAME)을 쓰며, 조회만 하고 아무것도 쓰지 않는다.
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
    f"?appName=checkVisitClips&authSource={mongoDbName}"
)

client = MongoClient(mongoUri, serverSelectionTimeoutMS=5000)
db = client[mongoDbName]

totalCount = db.visitClips.count_documents({})
print(f"visitClips 전체 문서 수: {totalCount}")

if totalCount == 0:
    print("아직 하나도 없음 - TOP 카메라 앞에서 사람이 감지될 만큼 머물렀다 벗어나 보세요.")
else:
    unmatchedCount = db.visitClips.count_documents({"matchedEventIds": []})
    withTracksCount = db.visitClips.count_documents({"trackIds": {"$ne": []}})
    print(f"matchedEventIds가 비어있는(=재학습 후보) 문서 수: {unmatchedCount}")
    print(
        f"trackIds가 채워진 문서 수: {withTracksCount}"
        " (tracking2.py가 아직 trackStarted를 안 보내므로 지금은 0이 정상)"
    )

    print("\n최근 5개:")
    cursor = db.visitClips.find(
        {},
        {"_id": 0, "cameraId": 1, "startedAt": 1, "endedAt": 1, "imageFileId": 1,
         "trackIds": 1, "matchedEventIds": 1, "unresolvedTrackIds": 1},
    ).sort("startedAt", -1).limit(5)
    for document in cursor:
        print(document)

topMediaFileCount = db["topMedia.files"].count_documents({})
print(f"\ntopMedia GridFS 파일 수(참고, visitClips 외 다른 경로 업로드분도 포함): {topMediaFileCount}")

client.close()
