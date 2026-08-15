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


mediaRepository = MediaRepository()
