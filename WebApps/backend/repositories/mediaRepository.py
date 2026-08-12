from repositories.mongoClient import getGridFsBucket


class MediaRepository:
    async def saveBytes(
        self,
        filename: str,
        data: bytes,
    ) -> str:
        bucket = getGridFsBucket()

        fileId = await bucket.upload_from_stream(
            filename, data
        )

        return str(fileId)


mediaRepository = MediaRepository()
