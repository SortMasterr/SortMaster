"""
motor(AsyncIOMotorClient) 접근 헬퍼 + GridFS 버킷.

.env의 MONGO_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME을 사용 — infra/checkEnv.py의
checkMongodb(), debug/db/testDbConnection.py와 동일한 URI 조립 규칙을 따름(값이
갈리지 않도록). DB_USER/DB_PASSWORD가 비어있으면 인증 없이 접속(로컬 Docker Mongo).

authSource를 DB_NAME으로 명시한다 — 안 넣으면 드라이버가 기본값인 admin DB를 인증
기준으로 삼는데, 계정을 DB_NAME(예: sortMaster)에 스코프해서 만들었으면
"Authentication failed"가 난다(둘이 다른 DB라서).

클라이언트를 모듈 import 시점에 즉시 생성하지 않고 getMongoDb() 호출 시점에 만든다.
motor 클라이언트는 생성될 때의 실행 중인 이벤트 루프에 바인딩되는데, uvicorn처럼
"앱 임포트 시점의 루프"와 "실제 요청을 처리하는 루프"가 갈리는 환경에서 import 시점에
바로 만들면 "Task ... attached to a different loop" 런타임 에러가 난다. 매 호출마다
현재 실행 중인 루프를 확인해서 달라졌으면 클라이언트를 다시 만들어 항상 올바른 루프에
바인딩되도록 한다.
"""
import asyncio
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorDatabase,
    AsyncIOMotorGridFSBucket,
)

from schemas.event import CameraId

load_dotenv()

mongoHost = os.getenv("MONGO_HOST", "localhost")
mongoPort = os.getenv("DB_PORT", "27020")
mongoUser = os.getenv("DB_USER")
mongoPassword = os.getenv("DB_PASSWORD")
mongoDbName = os.getenv("DB_NAME", "sortMaster")

if mongoUser and mongoPassword:
    _auth = f"{quote_plus(mongoUser)}:{quote_plus(mongoPassword)}@"
else:
    _auth = ""

mongoUri = (
    f"mongodb://{_auth}{mongoHost}:{mongoPort}/"
    f"?appName=sortMasterDB&authSource={mongoDbName}"
)

_client: AsyncIOMotorClient | None = None
_clientLoop: asyncio.AbstractEventLoop | None = None


def getMongoDb() -> AsyncIOMotorDatabase:
    global _client, _clientLoop

    loop = asyncio.get_event_loop()

    if _client is None or _clientLoop is not loop:
        _client = AsyncIOMotorClient(mongoUri)
        _clientLoop = loop

    return _client[mongoDbName]


def getGridFsBucket(
    cameraId: CameraId,
) -> AsyncIOMotorGridFSBucket:
    bucketName = (
        "topMedia"
        if cameraId == CameraId.ELEVTOP
        else "sideMedia"
    )

    return AsyncIOMotorGridFSBucket(
        getMongoDb(),
        bucket_name=bucketName,
    )
