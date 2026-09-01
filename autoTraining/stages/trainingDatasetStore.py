"""MongoDB 학습 데이터 원본에 승인 샘플을 등록하고 배치 스냅샷을 만듭니다."""
from __future__ import annotations
import asyncio
import hashlib
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import cv2
from common.pipelineUtilities import ManifestWriter, iterateManifest, manifestHasRows

def _fileSha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _validatedLabels(labelPath: Path, classCount: int) -> list[str]:
    lines = []
    for lineNumber, rawLine in enumerate(labelPath.read_text(encoding="utf-8").splitlines(), 1):
        parts = rawLine.split()
        if len(parts) != 5:
            raise ValueError(f"YOLO 라벨 열 개수가 5가 아닙니다: {labelPath}:{lineNumber}")
        try:
            classId = int(parts[0])
            coordinates = [float(value) for value in parts[1:]]
        except ValueError as error:
            raise ValueError(f"YOLO 라벨 숫자 형식 오류: {labelPath}:{lineNumber}") from error
        if not 0 <= classId < classCount:
            raise ValueError(f"YOLO classId 범위 오류: {labelPath}:{lineNumber}")
        if any(not 0.0 <= value <= 1.0 for value in coordinates):
            raise ValueError(f"YOLO 좌표 범위 오류: {labelPath}:{lineNumber}")
        lines.append(" ".join([str(classId), *(f"{value:.8f}".rstrip("0").rstrip(".") for value in coordinates)]))
    return lines

class TrainingDatasetStoreStage:
    """사람 승인 데이터의 MongoDB 등록과 재현 가능한 로컬 스냅샷을 담당합니다."""

    def _storeConfig(self) -> dict[str, Any]:
        return self.config["trainingDatasetStore"]

    async def _publishAsync(self) -> None:
        from motor.motor_asyncio import AsyncIOMotorGridFSBucket
        from pymongo.errors import DuplicateKeyError
        if not manifestHasRows(self.humanReviewsManifest):
            raise RuntimeError("먼저 humanReview 단계를 완료하세요.")
        mongoUri, databaseName = self._mongoUri()
        client = self._newMongoClient(mongoUri)
        database = client[databaseName]
        config = self._storeConfig()
        collection = database[str(config["samplesCollection"])]
        bucket = AsyncIOMotorGridFSBucket(database, bucket_name=str(config["imagesBucket"]))
        classes = list(self.config["dataset"]["classes"])
        inputMode = str(self.config["inference"]["inputMode"])
        publishedCount = skippedCount = 0
        try:
            await database.command("ping")
            await collection.create_index("imageSha256", unique=True)
            await collection.create_index([("status", 1), ("createdAt", 1)])
            with ManifestWriter(self.publishedSamplesManifest) as writer:
                for row in iterateManifest(self.humanReviewsManifest):
                    if row["humanReview"]["decision"] != "approved":
                        continue
                    labelPath = Path(row["labelPath"])
                    labels = _validatedLabels(labelPath, len(classes))
                    labelText = "\n".join(labels) + ("\n" if labels else "")
                    labelSha256 = hashlib.sha256(labelText.encode("utf-8")).hexdigest()
                    uploadPath = Path(row["imagePath"])
                    temporaryImage = None
                    if inputMode == "causal":
                        image = self._makeCausalInput(row)
                        temporaryImage = self.workspace / "publishImages" / f"{row['id']}.jpg"
                        temporaryImage.parent.mkdir(parents=True, exist_ok=True)
                        if not cv2.imwrite(str(temporaryImage), image):
                            raise OSError(f"MongoDB 등록용 causal 이미지 저장 실패: {temporaryImage}")
                        uploadPath = temporaryImage
                    try:
                        imageSha256 = _fileSha256(uploadPath)
                        existing = await collection.find_one({"imageSha256": imageSha256})
                        if existing is not None:
                            if (
                                existing.get("labelSha256") != labelSha256
                                or existing.get("classNames") != classes
                                or existing.get("inputMode") != inputMode
                            ):
                                raise RuntimeError(f"같은 이미지가 다른 학습 계약으로 이미 등록되어 있습니다: {row['id']}")
                            writer.write({"sampleId": str(existing["_id"]), "imageFileId": str(existing["imageFileId"]), "imageSha256": imageSha256, "status": "skippedDuplicate"})
                            skippedCount += 1
                            continue
                        sampleId = uuid.uuid4().hex
                        with uploadPath.open("rb") as imageFile:
                            imageFileId = await bucket.upload_from_stream(
                                f"{sampleId}{uploadPath.suffix.lower() or '.jpg'}", imageFile,
                                metadata={"sampleId": sampleId, "batchId": self.batchId, "imageSha256": imageSha256},
                            )
                        document = {
                            "_id": sampleId, "imageFileId": imageFileId, "imageSha256": imageSha256,
                            "labelSha256": labelSha256, "yoloLabels": labels, "classNames": classes,
                            "inputMode": inputMode, "imageExtension": uploadPath.suffix.lower() or ".jpg",
                            "status": "active", "source": "dailyHumanReview",
                            "sourceEventId": row.get("eventId"),
                            "sourceGroup": row.get("video") or row.get("eventId") or sampleId,
                            "batchId": self.batchId, "createdAt": datetime.now(timezone.utc),
                        }
                        try:
                            await collection.insert_one(document)
                        except DuplicateKeyError as error:
                            await bucket.delete(imageFileId)
                            raise RuntimeError(f"동시에 같은 이미지가 등록됐습니다: {row['id']}") from error
                        except Exception:
                            await bucket.delete(imageFileId)
                            raise
                        writer.write({"sampleId": sampleId, "imageFileId": str(imageFileId), "imageSha256": imageSha256, "status": "published"})
                        publishedCount += 1
                    finally:
                        if temporaryImage is not None:
                            temporaryImage.unlink(missing_ok=True)
        finally:
            client.close()
        if publishedCount + skippedCount == 0:
            raise RuntimeError("MongoDB에 등록할 사람 승인 데이터가 없습니다.")
        print(f"[PUBLISH] added={publishedCount}, duplicates={skippedCount}")

    def publishTrainingSamples(self) -> None:
        asyncio.run(self._publishAsync())

    async def _syncAsync(self) -> None:
        from motor.motor_asyncio import AsyncIOMotorGridFSBucket
        mongoUri, databaseName = self._mongoUri()
        client = self._newMongoClient(mongoUri)
        database = client[databaseName]
        config = self._storeConfig()
        collection = database[str(config["samplesCollection"])]
        bucket = AsyncIOMotorGridFSBucket(database, bucket_name=str(config["imagesBucket"]))
        classes = list(self.config["dataset"]["classes"])
        inputMode = str(self.config["inference"]["inputMode"])
        temporaryRoot = self.datasetSnapshotRoot.with_name(f".{self.datasetSnapshotRoot.name}.{os.getpid()}-{uuid.uuid4().hex}.tmp")
        count = 0
        try:
            await database.command("ping")
            (temporaryRoot / "images").mkdir(parents=True)
            (temporaryRoot / "labels").mkdir(parents=True)
            with ManifestWriter(temporaryRoot / "samples.jsonl") as writer:
                cursor = collection.find({"status": "active", "classNames": classes, "inputMode": inputMode}).sort([("_id", 1)])
                async for sample in cursor:
                    sampleId = str(sample["_id"])
                    extension = str(sample.get("imageExtension", ".jpg")).lower()
                    if extension not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                        extension = ".jpg"
                    imagePath = temporaryRoot / "images" / f"{sampleId}{extension}"
                    labelPath = temporaryRoot / "labels" / f"{sampleId}.txt"
                    with imagePath.open("wb") as output:
                        await bucket.download_to_stream(sample["imageFileId"], output)
                    if _fileSha256(imagePath) != sample["imageSha256"]:
                        raise RuntimeError(f"MongoDB 학습 이미지 해시 불일치: {sampleId}")
                    labels = sample.get("yoloLabels")
                    if not isinstance(labels, list) or not all(isinstance(line, str) for line in labels):
                        raise ValueError(f"MongoDB YOLO 라벨 형식 오류: {sampleId}")
                    labelText = "\n".join(labels) + ("\n" if labels else "")
                    labelPath.write_text(labelText, encoding="utf-8")
                    if hashlib.sha256(labelText.encode("utf-8")).hexdigest() != sample["labelSha256"]:
                        raise RuntimeError(f"MongoDB 학습 라벨 해시 불일치: {sampleId}")
                    finalImagePath = self.datasetSnapshotRoot / "images" / imagePath.name
                    finalLabelPath = self.datasetSnapshotRoot / "labels" / labelPath.name
                    writer.write({"sampleId": sampleId, "imagePath": str(finalImagePath.resolve()), "labelPath": str(finalLabelPath.resolve()), "imageSha256": sample["imageSha256"], "labelSha256": sample["labelSha256"], "sourceGroup": str(sample.get("sourceGroup") or sampleId), "batchId": sample.get("batchId")})
                    count += 1
            if count == 0:
                raise RuntimeError("MongoDB에 현재 계약과 일치하는 active 학습 데이터가 없습니다.")
            backupRoot = self.datasetSnapshotRoot.with_name(f".{self.datasetSnapshotRoot.name}.previous")
            if backupRoot.exists():
                shutil.rmtree(backupRoot)
            if self.datasetSnapshotRoot.exists():
                os.replace(self.datasetSnapshotRoot, backupRoot)
            try:
                os.replace(temporaryRoot, self.datasetSnapshotRoot)
            except Exception:
                if backupRoot.exists() and not self.datasetSnapshotRoot.exists():
                    os.replace(backupRoot, self.datasetSnapshotRoot)
                raise
            if backupRoot.exists():
                shutil.rmtree(backupRoot)
        finally:
            client.close()
            if temporaryRoot.exists():
                shutil.rmtree(temporaryRoot)
        print(f"[SYNC DATASET] active samples={count}: {self.datasetSnapshotRoot}")

    def syncTrainingDataset(self) -> None:
        asyncio.run(self._syncAsync())

def publishTrainingSamples(pipeline: TrainingDatasetStoreStage) -> None:
    pipeline.publishTrainingSamples()

def syncTrainingDataset(pipeline: TrainingDatasetStoreStage) -> None:
    pipeline.syncTrainingDataset()
