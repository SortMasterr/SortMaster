"""0단계: MongoDB 이벤트와 GridFS 클립을 일일 학습 입력으로 수집합니다."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

from common.pipelineUtilities import ManifestWriter


class CollectEventMediaStage:
    """이벤트 저장소를 읽기 전용으로 조회해 배치별 원본 클립을 준비합니다.

    운영 계약상 YOLO 재학습 대상은 TOP 카메라의 투기(misclassification) 이벤트입니다.
    SIDE 카메라의 overflow 영상은 다른 모델의 데이터이므로 이 파이프라인에 섞지 않습니다.
    MongoDB 문서를 수정하거나 GridFS 원본을 삭제하지 않고 로컬 작업공간에 사본만 만듭니다.
    """

    @staticmethod
    def _batchRangeUtc(batchId: str, utcOffsetHours: float) -> tuple[datetime, datetime]:
        """YYYY-MM-DD 배치의 현지 하루 범위를 MongoDB 조회용 UTC 범위로 바꿉니다."""
        try:
            localStart = datetime.strptime(batchId, "%Y-%m-%d").replace(
                tzinfo=timezone(timedelta(hours=utcOffsetHours))
            )
        except ValueError as error:
            raise ValueError(
                "GridFS 수집을 사용할 때 batchId는 YYYY-MM-DD 형식이어야 합니다."
            ) from error
        return localStart.astimezone(timezone.utc), (localStart + timedelta(days=1)).astimezone(timezone.utc)

    @staticmethod
    def _mongoUri() -> tuple[str, str]:
        """백엔드와 동일한 환경변수 규칙으로 URI와 DB 이름을 구성합니다."""
        from dotenv import load_dotenv

        load_dotenv()
        host = os.getenv("MONGO_HOST", "localhost")
        port = os.getenv("DB_PORT", "27020")
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")
        databaseName = os.getenv("DB_NAME", "sortMaster")
        authentication = (
            f"{quote_plus(user)}:{quote_plus(password)}@"
            if user and password else ""
        )
        uri = (
            f"mongodb://{authentication}{host}:{port}/"
            f"?appName=sortMasterTraining&authSource={databaseName}"
        )
        return uri, databaseName

    async def _collectFromGridFs(self) -> None:
        """이벤트를 시간순으로 읽고 참조된 GridFS GIF를 안전하게 내려받습니다."""
        from bson import ObjectId
        from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
        from pymongo.errors import PyMongoError

        sourceConfig = self.config["eventStore"]
        startUtc, endUtc = self._batchRangeUtc(
            self.batchId, float(sourceConfig.get("utcOffsetHours", 9))
        )
        mongoUri, databaseName = self._mongoUri()
        client = AsyncIOMotorClient(
            mongoUri,
            serverSelectionTimeoutMS=int(sourceConfig.get("serverSelectionTimeoutMs", 5000)),
        )
        database = client[databaseName]
        bucket = AsyncIOMotorGridFSBucket(database, bucket_name="topMedia")
        query = {
            "timestamp": {"$gte": startUtc, "$lt": endUtc},
            "cameraId": "ELEV-TOP",
            "eventCategory": "misclassification",
            "imageFileId": {"$type": "string", "$ne": ""},
        }
        downloadedFileIds: set[str] = set()
        collectedCount = 0
        try:
            await database.command("ping")
            cursor = database["events"].find(query).sort([("timestamp", 1), ("eventId", 1)])
            with ManifestWriter(self.collectedMediaManifest) as writer:
                async for event in cursor:
                    fileId = str(event["imageFileId"])
                    # 여러 이벤트가 같은 클립을 참조하더라도 GridFS 다운로드는 한 번만 수행한다.
                    if fileId in downloadedFileIds:
                        continue
                    try:
                        objectId = ObjectId(fileId)
                    except Exception as error:
                        print(f"[WARN] 잘못된 imageFileId 건너뜀: eventId={event.get('eventId')} fileId={fileId}")
                        continue

                    targetPath = self.videosDirectory / f"{event['eventId']}.gif"
                    targetPath.parent.mkdir(parents=True, exist_ok=True)
                    temporaryPath = targetPath.with_suffix(".gif.part")
                    try:
                        with temporaryPath.open("wb") as outputFile:
                            await bucket.download_to_stream(objectId, outputFile)
                        os.replace(temporaryPath, targetPath)
                    except Exception:
                        temporaryPath.unlink(missing_ok=True)
                        raise

                    timestamp = event.get("timestamp")
                    writer.write({
                        "eventId": event["eventId"],
                        "detectionId": event.get("detectionId"),
                        "cameraId": event["cameraId"],
                        "eventCategory": event["eventCategory"],
                        "imageFileId": fileId,
                        "modelVersion": event.get("modelVersion"),
                        "timestamp": timestamp.isoformat() if timestamp else None,
                        "mediaPath": str(targetPath.resolve()),
                    })
                    downloadedFileIds.add(fileId)
                    collectedCount += 1
        except PyMongoError as error:
            raise RuntimeError(f"이벤트 저장소/GridFS 수집 실패: {error}") from error
        finally:
            client.close()

        if collectedCount == 0:
            raise RuntimeError(
                f"{self.batchId}에 imageFileId가 있는 ELEV-TOP 투기 이벤트가 없습니다."
            )
        print(f"[COLLECT] GridFS 이벤트 클립 {collectedCount}개: {self.videosDirectory}")

    def collect(self) -> None:
        """설정된 저장소 유형에 맞게 배치 입력을 준비합니다."""
        sourceType = str(self.config["eventStore"].get("source", "gridFs"))
        if sourceType == "localDirectory":
            # 개발용 모드에서는 사용자가 inputVideos/<batchId>에 넣은 파일을 그대로 사용한다.
            print(f"[COLLECT] localDirectory 사용: {self.videosDirectory}")
            return
        if sourceType != "gridFs":
            raise ValueError("eventStore.source는 gridFs 또는 localDirectory여야 합니다.")
        asyncio.run(self._collectFromGridFs())


def collectEventMedia(pipeline: CollectEventMediaStage) -> None:
    """오케스트레이터에서 이벤트 저장소 수집 단계를 실행합니다."""
    pipeline.collect()