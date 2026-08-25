"""Qwen 검수 결과 전체에 사람의 최종 결정을 적용하는 승인 게이트입니다.

UI가 아직 없어도 동일한 계약을 사용할 수 있도록 사람이 작성하는 humanDecisions.jsonl과
파이프라인이 검증해 만드는 humanReviews.jsonl을 분리합니다. Build는 검증 완료 파일만 읽습니다.
"""
from pathlib import Path
from typing import Any

from common.pipelineUtilities import ManifestWriter, iterateManifest, manifestHasRows


class HumanReviewStage:
    """모든 Qwen 결과에 누락 없는 사람 결정을 요구합니다."""

    def exportHumanReviewQueue(self) -> None:
        """Qwen 판정과 무관하게 모든 항목을 사람 최종 검수 큐에 넣습니다."""
        if not manifestHasRows(self.reviewsManifest):
            raise RuntimeError("Qwen 검수 결과가 없어 사람 검수 큐를 만들 수 없습니다.")
        count = 0
        with ManifestWriter(self.humanReviewQueue) as writer:
            for row in iterateManifest(self.reviewsManifest):
                output = dict(row)
                output["batchId"] = self.batchId
                output["humanDecision"] = None
                writer.write(output)
                count += 1
        print(f"[HUMAN REVIEW] 큐 생성: {count}개 -> {self.humanReviewQueue}")
        print(f"[HUMAN REVIEW] 결정 파일 작성 필요: {self.humanDecisionsManifest}")

    def humanReview(self) -> None:
        if not manifestHasRows(self.humanReviewQueue):
            raise RuntimeError("먼저 review 단계를 실행하세요.")
        if not manifestHasRows(self.humanDecisionsManifest):
            raise RuntimeError(
                f"사람 검수 결정이 없습니다: {self.humanDecisionsManifest}. "
                "humanReviewQueue.jsonl의 모든 id를 승인 또는 거절하세요."
            )

        decisions: dict[str, dict[str, Any]] = {}
        for decision in iterateManifest(self.humanDecisionsManifest):
            itemId = str(decision.get("id", ""))
            if not itemId or itemId in decisions:
                raise ValueError(f"사람 검수 id가 없거나 중복됩니다: {itemId}")
            if decision.get("decision") not in {"approved", "rejected"}:
                raise ValueError(f"사람 검수 decision은 approved/rejected만 허용합니다: {itemId}")
            decisions[itemId] = decision

        queueIds = {str(row["id"]) for row in iterateManifest(self.humanReviewQueue)}
        extraIds = set(decisions) - queueIds
        if extraIds:
            raise RuntimeError(f"현재 배치에 없는 사람 검수 id가 있습니다: {sorted(extraIds)}")

        approvedCount = rejectedCount = 0
        with ManifestWriter(self.humanReviewsManifest) as writer:
            for row in iterateManifest(self.humanReviewQueue):
                itemId = str(row["id"])
                if itemId not in decisions:
                    raise RuntimeError(f"사람 검수가 누락됐습니다: {itemId}")
                decision = decisions[itemId]
                output = dict(row)
                labelPath = Path(decision.get("labelPath") or row["labelPath"])
                if decision["decision"] == "approved" and not labelPath.is_file():
                    raise FileNotFoundError(f"승인 라벨 파일이 없습니다: {labelPath}")
                output["labelPath"] = str(labelPath.resolve())
                output["humanReview"] = {
                    "decision": decision["decision"],
                    "reviewer": str(decision.get("reviewer", "")),
                    "reviewedAt": decision.get("reviewedAt"),
                    "notes": str(decision.get("notes", "")),
                }
                writer.write(output)
                if decision["decision"] == "approved":
                    approvedCount += 1
                else:
                    rejectedCount += 1

        print(f"[HUMAN REVIEW] approved={approvedCount}, rejected={rejectedCount}")


def validateHumanReview(pipeline: HumanReviewStage) -> None:
    pipeline.humanReview()
