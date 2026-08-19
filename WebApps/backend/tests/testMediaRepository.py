import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId

from repositories.mediaRepository import MediaRepository
from schemas.event import CameraId


class MediaRepositoryTest(unittest.IsolatedAsyncioTestCase):
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
