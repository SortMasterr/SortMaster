"""4단계: Qwen-VL로 YOLO 자동 라벨을 검수하고 상태별로 분류합니다."""

import base64
import json
import os
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from common.pipelineUtilities import (
    ManifestWriter,
    chinesePattern,
    iterateManifest,
    manifestHasRows,
)


class ReviewLabelsStage:
    """Qwen-VL 요청, 응답 검증, 검수 결과 분류를 담당합니다."""
    def _resolveQwenVlApiBaseUrl(self) -> str:
        """``LLM_PORT`` 환경변수로 vLLM OpenAI 호환 API 주소를 구성합니다.

        프로젝트 루트 환경파일을 우선하고 백엔드 환경파일은 누락된 값만 보완합니다.
        포트는 설정 파일이나 소스에 중복 기록하지 않으며 유효 범위를 호출 전에 검증합니다.
        """
        from dotenv import load_dotenv

        load_dotenv(self.projectRoot / ".env", override=False)
        load_dotenv(self.projectRoot / "WebApps" / "backend" / ".env", override=False)
        portValue = os.getenv("LLM_PORT")
        if portValue is None:
            raise RuntimeError(
                "LLM_PORT가 없습니다. 프로젝트 루트 또는 WebApps/backend/.env에 설정하세요."
            )
        try:
            port = int(portValue)
        except ValueError as error:
            raise ValueError("LLM_PORT는 정수 포트 번호여야 합니다.") from error
        if not 1 <= port <= 65535:
            raise ValueError("LLM_PORT는 1~65535 범위여야 합니다.")

        apiHost = str(self.config["qwenVl"].get("apiHost", "127.0.0.1")).rstrip("/")
        if not apiHost.startswith(("http://", "https://")):
            raise ValueError("qwenVl.apiHost는 http:// 또는 https://로 시작해야 합니다.")
        return f"{apiHost}:{port}"

    def _requestQwenVl(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """설정된 Qwen-VL API 서버로 JSON 요청을 전송합니다.

        프로젝트 Compose의 vLLM OpenAI 호환 API를 사용합니다.
        모델 목록은 /v1/models, 검수 요청은 /v1/chat/completions로 호출합니다.
        """
        apiBaseUrl = self._resolveQwenVlApiBaseUrl()
        requestData = (
            None
            if payload is None
            else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )
        request = urllib.request.Request(
            apiBaseUrl + endpoint,
            data=requestData,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        timeoutSeconds = float(self.config["qwenVl"]["timeoutSeconds"])
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeoutSeconds,
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as error:
            raise RuntimeError(
                f"Qwen-VL API 연결 실패: {error}"
            ) from error

    def _resolveQwenVlModel(self) -> str:
        """설정 모델을 사용하거나 설치 목록에서 Qwen-VL 모델을 자동 선택합니다."""
        configuredModel = str(self.config["qwenVl"].get("model", "auto"))
        if configuredModel.lower() != "auto":
            return configuredModel

        response = self._requestQwenVl("GET", "/v1/models")
        modelNames = [
            str(model.get("id", ""))
            for model in response.get("data", [])
        ]
        qwenVlModels = [
            name
            for name in modelNames
            if "qwen" in name.lower() and "vl" in name.lower()
        ]
        if not qwenVlModels:
            raise RuntimeError(
                "Qwen-VL 모델을 찾지 못했습니다. qwenVl.model에 "
                f"정확한 모델명을 입력하세요. 설치 모델: {modelNames}"
            )
        print(f"[QWEN-VL] 자동 선택 모델: {qwenVlModels[0]}")
        return qwenVlModels[0]

    def _reviewSchema(self) -> dict[str, Any]:
        """Qwen-VL이 반환해야 하는 camelCase JSON 구조를 정의합니다."""
        classes = self.config["dataset"]["classes"]
        return {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["approved", "rejected", "manualReview"],
                },
                "predictedClass": {
                    "type": "string",
                    "enum": classes + ["none", "multiple"],
                },
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "none",
                            "wrongClass",
                            "missingObject",
                            "extraBox",
                            "badBbox",
                            "tooBlurry",
                            "tooDark",
                            "multipleObjects",
                        ],
                    },
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
            },
            "required": [
                "decision",
                "predictedClass",
                "issues",
                "confidence",
            ],
            "additionalProperties": False,
        }

    def _validateReview(self, content: str) -> dict[str, Any]:
        """Qwen-VL 응답의 JSON 형식과 허용값을 후속 처리 전에 검증합니다."""
        if chinesePattern.search(content):
            raise ValueError("Qwen-VL 응답에 허용하지 않는 중국어 문자가 있습니다.")

        review = json.loads(content)
        schema = self._reviewSchema()
        properties = schema["properties"]
        if review.get("decision") not in properties["decision"]["enum"]:
            raise ValueError("허용되지 않는 decision입니다.")
        if review.get("predictedClass") not in properties["predictedClass"]["enum"]:
            raise ValueError("허용되지 않는 predictedClass입니다.")

        allowedIssues = set(properties["issues"]["items"]["enum"])
        issues = review.get("issues")
        if not isinstance(issues, list) or not set(issues) <= allowedIssues:
            raise ValueError("허용되지 않는 issues입니다.")

        confidence = float(review.get("confidence", -1))
        if not 0 <= confidence <= 1:
            raise ValueError("confidence는 0과 1 사이여야 합니다.")
        review["confidence"] = confidence
        return review

    def _reviewOne(
        self,
        qwenVlModel: str,
        row: dict[str, Any],
    ) -> dict[str, Any]:
        """원본과 bbox 표시 이미지를 Qwen-VL에 보내 한 프레임을 검수합니다."""
        classes = self.config["dataset"]["classes"]
        detections = [
            {
                "class": classes[item["classId"]],
                "confidence": round(item["confidence"], 4),
                "xyxy": [round(value, 1) for value in item["xyxy"]],
            }
            for item in row["detections"]
        ]
        prompt = (
            "첫 번째 이미지는 원본 CCTV 프레임이고 두 번째 이미지는 "
            "YOLO bbox 표시 이미지다. 객체의 클래스와 bbox가 적절한지 검수하라. "
            "쓰레기통 자체는 검수 대상이 아니다. 반드시 제공된 JSON schema만 "
            "출력하고 중국어와 자연어 설명은 출력하지 마라. "
            f"허용 클래스: {classes}. YOLO 결과: "
            f"{json.dumps(detections, ensure_ascii=False)}"
        )
        imageContents = []
        for imagePathValue in (row["imagePath"], row["annotatedPath"]):
            encoded = base64.b64encode(Path(imagePathValue).read_bytes()).decode("ascii")
            imageContents.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
            })
        payload = {
            "model": qwenVlModel,
            "messages": [{
                "role": "user",
                "content": [{"type": "text", "text": prompt}, *imageContents],
            }],
            "temperature": 0,
            "seed": 42,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "labelReview",
                    "strict": True,
                    "schema": self._reviewSchema(),
                },
            },
        }
        response = self._requestQwenVl("POST", "/v1/chat/completions", payload)
        return self._validateReview(response["choices"][0]["message"]["content"])

    def review(self) -> None:
        """자동 라벨을 순차 검수하여 reviews.jsonl과 상태별 폴더에 저장합니다."""
        if not manifestHasRows(self.labelsManifest):
            raise RuntimeError("먼저 label 단계를 실행하세요.")

        qwenVlModel = self._resolveQwenVlModel()
        retries = int(self.config["qwenVl"]["retries"])
        minimumConfidence = float(
            self.config["qwenVl"]["minimumReviewConfidence"]
        )
        counts = {
            name: 0
            for name in ("approved", "rejected", "manualReview")
        }
        processedCount = 0

        # 결과를 즉시 기록하여 긴 영상에서도 전체 응답이 RAM에 쌓이지 않게 합니다.
        with ManifestWriter(self.reviewsManifest) as writer:
            for row in iterateManifest(self.labelsManifest):
                review = None
                errors = []
                for attempt in range(retries + 1):
                    try:
                        review = self._reviewOne(qwenVlModel, row)
                        break
                    except (
                        ValueError,
                        RuntimeError,
                        KeyError,
                        json.JSONDecodeError,
                    ) as error:
                        errors.append(f"attempt {attempt + 1}: {error}")
                        time.sleep(min(2 ** attempt, 5))

                # 서버 오류나 잘못된 응답은 자동 승인하지 않고 사람 검수로 보냅니다.
                if review is None:
                    review = {
                        "decision": "manualReview",
                        "predictedClass": "none",
                        "issues": ["badBbox"],
                        "confidence": 0.0,
                    }
                riskyIssues = {
                    "wrongClass",
                    "badBbox",
                    "missingObject",
                    "extraBox",
                    "multipleObjects",
                }
                if (
                    review["confidence"] < minimumConfidence
                    or any(
                        issue in riskyIssues
                        for issue in review["issues"]
                    )
                ):
                    review["decision"] = "manualReview"

                output = dict(row)
                output.update({
                    "review": review,
                    "reviewErrors": errors,
                    "qwenVlModel": qwenVlModel,
                })
                writer.write(output)
                counts[review["decision"]] += 1

                queueRoot = {
                    "approved": self.approvedRoot,
                    "rejected": self.rejectedRoot,
                    "manualReview": self.manualRoot,
                }[review["decision"]]
                queueDirectory = queueRoot / row["video"]
                queueDirectory.mkdir(parents=True, exist_ok=True)
                shutil.copy2(
                    row["imagePath"],
                    queueDirectory / f"{row['id']}.jpg",
                )
                shutil.copy2(
                    row["annotatedPath"],
                    queueDirectory / f"{row['id']}__annotated.jpg",
                )
                shutil.copy2(
                    row["labelPath"],
                    queueDirectory / f"{row['id']}.txt",
                )

                processedCount += 1
                if processedCount % 25 == 0:
                    print(f"[REVIEW] {processedCount}개 처리")

        print(f"[REVIEW] {counts}")


def reviewLabels(pipeline: ReviewLabelsStage) -> None:
    """오케스트레이터에서 Qwen-VL 검수 단계를 실행합니다."""
    pipeline.review()
    # Qwen의 approved/rejected도 오판할 수 있으므로 모든 결과를 사람 검수 큐로 보냅니다.
    pipeline.exportHumanReviewQueue()
