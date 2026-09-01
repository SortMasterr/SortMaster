"""BIN_STATES 저장소 — `binId`당 최신 상태 1행만 유지하는 upsert 컬렉션(Docs/ERD.md 참고).

이력은 EVENT(overflow)가 담당하므로 이 컬렉션은 상태 이력을 쌓지 않는다.
"""
import logging
from datetime import datetime, timezone

from repositories.mongoClient import getMongoDb
from schemas.binState import BinCurrentState, BinState
from schemas.event import BinType, CameraId


logger = logging.getLogger(__name__)

_legacyBinTypeValues = {
    "general": BinType.NORMAL,
    "plasticCan": BinType.RECYCLABLES,
}


class BinStateRepository:
    def __init__(self):
        self.indexesReady = False

    @property
    def collection(self):
        return getMongoDb()["binStates"]

    def _toDocument(self, binState: BinState) -> dict:
        document = binState.model_dump()
        document["cameraId"] = binState.cameraId.value
        document["binType"] = binState.binType.value
        document["currentState"] = binState.currentState.value

        return document

    def _fromDocument(self, document: dict) -> BinState:
        return BinState(
            binId=document["binId"],
            cameraId=CameraId(document["cameraId"]),
            binType=_parseBinType(document["binType"]),
            sessionId=document["sessionId"],
            currentState=BinCurrentState(document["currentState"]),
            confidenceScore=document["confidenceScore"],
            overflowDuration=document["overflowDuration"],
            lastChangedAt=self.normalizeDateTime(
                document["lastChangedAt"]
            ),
            activeOverflowEventId=document.get("activeOverflowEventId"),
        )

    def _tryFromDocument(self, document: dict) -> BinState | None:
        try:
            return self._fromDocument(document)
        except (KeyError, TypeError, ValueError) as error:
            logger.warning(
                "Skipping incompatible binState document %r: %s",
                document.get("_id"),
                error,
            )
            return None

    async def ensureIndexes(self) -> None:
        if self.indexesReady:
            return

        await self.collection.create_index(
            "binId",
            unique=True,
            name="uq_binStates_binId",
        )
        self.indexesReady = True

    async def findById(self, binId: str) -> BinState | None:
        document = await self.collection.find_one({"binId": binId})

        return (
            self._tryFromDocument(document)
            if document is not None
            else None
        )

    async def findAll(self) -> list[BinState]:
        cursor = self.collection.find({}).sort("binId", 1)
        latestByBinId: dict[str, BinState] = {}

        async for document in cursor:
            binState = self._tryFromDocument(document)

            if binState is None:
                continue

            existing = latestByBinId.get(binState.binId)

            if (
                existing is None
                or binState.lastChangedAt > existing.lastChangedAt
            ):
                latestByBinId[binState.binId] = binState

        return sorted(
            latestByBinId.values(),
            key=lambda item: item.binId,
        )

    async def upsert(self, binState: BinState) -> BinState:
        await self.ensureIndexes()

        await self.collection.update_one(
            {"binId": binState.binId},
            {"$set": self._toDocument(binState)},
            upsert=True,
        )

        return binState

    def normalizeDateTime(self, dateTime: datetime) -> datetime:
        if dateTime.tzinfo is None:
            return dateTime.replace(tzinfo=timezone.utc)

        return dateTime


binStateRepository = BinStateRepository()


def _parseBinType(value: str) -> BinType:
    if value in _legacyBinTypeValues:
        return _legacyBinTypeValues[value]
    return BinType(value)
