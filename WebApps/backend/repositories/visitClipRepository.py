import logging

from bson import ObjectId

from repositories.mongoClient import getMongoDb
from schemas.event import CameraId
from schemas.visitClip import VisitClip

logger = logging.getLogger(__name__)


class VisitClipRepository:
    def __init__(self):
        self.indexesReady = False

    @property
    def collection(self):
        return getMongoDb()["visitClips"]

    def _toDocument(self, clip: VisitClip) -> dict:
        document = clip.model_dump()
        document["cameraId"] = clip.cameraId.value
        return document

    def _fromDocument(self, document: dict) -> VisitClip:
        return VisitClip(
            cameraId=CameraId(document["cameraId"]),
            startedAt=document["startedAt"],
            endedAt=document["endedAt"],
            imageFileId=document["imageFileId"],
            trackIds=document.get("trackIds", []),
            matchedEventIds=document.get("matchedEventIds", []),
            unresolvedTrackIds=document.get("unresolvedTrackIds", []),
        )

    async def ensureIndexes(self) -> None:
        if self.indexesReady:
            return

        # trackIds는 배열 필드 — MongoDB가 자동으로 multikey 인덱스를 만들어서
        # {"trackIds": trackId} 단일 값 쿼리(포함 여부)에 그대로 사용 가능.
        await self.collection.create_index("trackIds")
        await self.collection.create_index(
            [("cameraId", 1), ("startedAt", -1)]
        )
        self.indexesReady = True

    async def save(self, clip: VisitClip) -> None:
        await self.ensureIndexes()
        await self.collection.insert_one(self._toDocument(clip))

    async def findByTrackId(self, trackId: int) -> VisitClip | None:
        await self.ensureIndexes()
        document = await self.collection.find_one({"trackIds": trackId})
        return self._fromDocument(document) if document is not None else None

    async def addMatchedEvent(self, trackId: int, eventId: str) -> bool:
        """clip 생성 이후에 뒤늦게 도착한 aiDisposal을 위한 폴백 매칭.

        일반적인 순서(트랙이 사람 방문 중에 확정되는 경우)는 아직 만들어지지 않은
        clip을 대신할 메모리 저장소(services/visitClipService.py의 activeTracks)에서
        처리되므로, 여기까지 오는 건 드문 순서(clip이 먼저 저장된 뒤 결과가 도착)뿐이다.
        """
        await self.ensureIndexes()
        result = await self.collection.update_one(
            {"trackIds": trackId},
            {"$addToSet": {"matchedEventIds": eventId}},
        )
        return result.matched_count > 0

    async def addUnresolvedTrack(self, trackId: int) -> bool:
        """addMatchedEvent와 동일한 이유로, clip 저장 이후 도착한 trackEnded 전용 폴백."""
        await self.ensureIndexes()
        result = await self.collection.update_one(
            {"trackIds": trackId},
            {"$addToSet": {"unresolvedTrackIds": trackId}},
        )
        return result.matched_count > 0

    async def getImageFileId(self, trackId: int) -> str | None:
        await self.ensureIndexes()
        document = await self.collection.find_one(
            {"trackIds": trackId},
            {"imageFileId": 1},
        )
        return document["imageFileId"] if document is not None else None

    async def listRecent(self, limit: int = 60) -> list[dict]:
        """관리자 웹에서 방문 클립을 최신순으로 훑어보기 위한 목록 조회."""
        await self.ensureIndexes()
        cursor = self.collection.find().sort("startedAt", -1).limit(limit)
        return [
            {
                "id": str(document["_id"]),
                "cameraId": document["cameraId"],
                "startedAt": document["startedAt"],
                "endedAt": document["endedAt"],
                "trackIds": document.get("trackIds", []),
                "matchedEventIds": document.get("matchedEventIds", []),
                "unresolvedTrackIds": document.get("unresolvedTrackIds", []),
            }
            async for document in cursor
        ]

    async def findMediaById(self, clipId: str) -> tuple[str, CameraId] | None:
        """클립의 GridFS 파일 ID와 어느 버킷(카메라)에 있는지 함께 반환한다."""
        await self.ensureIndexes()
        document = await self.collection.find_one(
            {"_id": ObjectId(clipId)},
            {"imageFileId": 1, "cameraId": 1},
        )
        if document is None:
            return None
        return document["imageFileId"], CameraId(document["cameraId"])


visitClipRepository = VisitClipRepository()
