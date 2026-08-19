from bson import ObjectId

from repositories.mongoClient import getGridFsBucket
from schemas.event import CameraId


class MediaRepository:
    async def saveBytes(
        self,
        filename: str,
        data: bytes,
        cameraId: CameraId,
    ) -> str:
        bucket = getGridFsBucket(cameraId)

        fileId = await bucket.upload_from_stream(
            filename, data
        )

        return str(fileId)

    async def deleteById(
        self,
        fileId: str,
        cameraId: CameraId,
    ) -> None:
        bucket = getGridFsBucket(cameraId)
        await bucket.delete(ObjectId(fileId))


mediaRepository = MediaRepository()
