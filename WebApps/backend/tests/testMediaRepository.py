import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId

from repositories.mediaRepository import MediaRepository
from schemas.event import CameraId


class MediaRepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def testGetBytesUsesCameraBucketAndObjectId(self):
        repository = MediaRepository()
        bucket = AsyncMock()
        stream = AsyncMock()
        stream.read.return_value = b"gif-data"
        bucket.open_download_stream.return_value = stream
        fileId = "507f1f77bcf86cd799439011"

        with patch(
            "repositories.mediaRepository.getGridFsBucket",
            return_value=bucket,
        ) as getBucket:
            result = await repository.getBytesById(
                fileId,
                CameraId.ELEVTOP,
            )

        self.assertEqual(b"gif-data", result)
        getBucket.assert_called_once_with(CameraId.ELEVTOP)
        bucket.open_download_stream.assert_awaited_once_with(
            ObjectId(fileId)
        )

    async def testGetBytesRejectsInvalidObjectId(self):
        repository = MediaRepository()

        result = await repository.getBytesById(
            "not-an-object-id",
            CameraId.ELEVTOP,
        )

        self.assertIsNone(result)

    async def testDeleteUsesCameraBucketAndObjectId(self):
        repository = MediaRepository()
        bucket = AsyncMock()
        fileId = "507f1f77bcf86cd799439011"

        with patch(
            "repositories.mediaRepository.getGridFsBucket",
            return_value=bucket,
        ) as getBucket:
            await repository.deleteById(
                fileId,
                CameraId.ELEVTOP,
            )

        getBucket.assert_called_once_with(CameraId.ELEVTOP)
        bucket.delete.assert_awaited_once_with(
            ObjectId(fileId)
        )


if __name__ == "__main__":
    unittest.main()
