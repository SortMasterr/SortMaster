from bson import ObjectId
from gridfs.errors import NoFile

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

    async def getBytesById(
        self,
        fileId: str,
        cameraId: CameraId,
    ) -> bytes | None:
        if not ObjectId.is_valid(fileId):
            return None

        bucket = getGridFsBucket(cameraId)

        try:
            stream = await bucket.open_download_stream(
                ObjectId(fileId)
            )
        except NoFile:
            return None

        return await stream.read()


mediaRepository = MediaRepository()
