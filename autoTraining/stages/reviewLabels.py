"""4단계: Qwen-VL로 YOLO 자동 라벨을 검수하고 상태별로 분류합니다."""

import base64
import json
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from common.pipelineUtilities import chinesePattern, readManifest, writeManifest


class ReviewLabelsStage:
    """Qwen-VL 요청, 응답 검증, 검수 큐 분류의 실제 구현입니다."""

    def _ollama_request(self, method: str, endpoint: str, payload=None) -> dict[str, Any]:
        """Ollama의 HTTP API를 호출하는 최소 공통 함수입니다.

        base_url과 timeout은 설정에서 읽습니다. 요청 본문이 있으면 UTF-8 JSON으로 직렬화하고,
        네트워크 오류는 어느 서버 연결이 실패했는지 알 수 있는 RuntimeError로 변환합니다.
        모델 선택과 실제 이미지 검수 요청이 동일한 통신 처리를 공유하도록 분리했습니다.
        """
        base_url = self.config["ollama"]["base_url"].rstrip("/")
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            base_url + endpoint,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        timeout = float(self.config["ollama"]["timeout_seconds"])
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as error:
            raise RuntimeError(f"Ollama 연결 실패: {base_url} ({error})") from error

    def _resolve_ollama_model(self) -> str:
        """설정된 모델을 사용하거나 설치된 Qwen-VL 모델을 자동으로 선택합니다."""
        configured = str(self.config["ollama"].get("model", "auto"))
        if configured.lower() != "auto":
            return configured
        response = self._ollama_request("GET", "/api/tags")
        names = [str(model.get("name", "")) for model in response.get("models", [])]
        candidates = [name for name in names if "qwen" in name.lower() and "vl" in name.lower()]
        if not candidates:
            raise RuntimeError(
                "Ollama에서 Qwen-VL 모델을 찾지 못했습니다. ollama list 결과의 "
                "비전 모델명을 config.yaml의 ollama.model에 입력하세요. "
                f"설치 모델: {names}"
            )
        print(f"[OLLAMA] 자동 선택 모델: {candidates[0]}")
        return candidates[0]

    def _review_schema(self) -> dict[str, Any]:
        """Qwen-VL이 자유 문장 대신 반환해야 하는 JSON 구조를 정의합니다.

        decision은 approved, manual_review, rejected 중 하나여야 하며, predicted_class와
        issues도 허용 목록 안에서만 선택할 수 있습니다. 구조를 제한하면 자연어 표현 차이로
        자동 처리 로직이 흔들리는 문제를 줄이고 잘못된 응답을 수동 검수로 보낼 수 있습니다.
        """
        classes = self.config["dataset"]["classes"]
        return {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["approved", "rejected", "manual_review"],
                },
                "predicted_class": {
                    "type": "string",
                    "enum": classes + ["none", "multiple"],
                },
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "none", "wrong_class", "missing_object", "extra_box",
                            "bad_bbox", "too_blurry", "too_dark", "multiple_objects",
                        ],
                    },
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["decision", "predicted_class", "issues", "confidence"],
            "additionalProperties": False,
        }

    def _validate_review(self, content: str) -> dict[str, Any]:
        """Qwen-VL 응답을 신뢰하기 전에 형식과 값의 범위를 검증합니다.

        JSON 파싱 가능 여부, 허용된 decision과 class인지, issues 목록이 유효한지,
        confidence가 0~1인지 확인합니다. 예상하지 못한 자연어·문자나 잘못된 값은 예외로
        처리하여 review 단계의 재시도 또는 manual_review 안전 경로로 보내게 합니다.
        """
        if chinesePattern.search(content):
            raise ValueError("중국어 문자가 포함됨")
        review = json.loads(content)
        schema = self._review_schema()
        if review.get("decision") not in schema["properties"]["decision"]["enum"]:
            raise ValueError("허용되지 않은 decision")
        if review.get("predicted_class") not in schema["properties"]["predicted_class"]["enum"]:
            raise ValueError("허용되지 않은 class")
        allowed_issues = set(schema["properties"]["issues"]["items"]["enum"])
        if not isinstance(review.get("issues"), list) or not set(review["issues"]) <= allowed_issues:
            raise ValueError("허용되지 않은 issues")
        confidence = float(review.get("confidence", -1))
        if not 0 <= confidence <= 1:
            raise ValueError("confidence 범위 오류")
        review["confidence"] = confidence
        return review

    def _review_one(self, model: str, row: dict[str, Any]) -> dict[str, Any]:
        """한 프레임의 자동 라벨이 학습에 사용 가능한지 Qwen-VL에 질문합니다.

        원본 이미지와 bbox 시각화 이미지를 함께 보내 객체의 실제 모습과 YOLO 예측을 비교하게
        합니다. 모델에는 허용 클래스, 기존 탐지 좌표와 신뢰도, 출력 JSON 스키마를 전달합니다.
        반환값은 후속 단계가 사용할 decision, predicted_class, issues, confidence 정보입니다.
        Qwen-VL은 bbox를 직접 수정하지 않으며 애매한 항목은 사람이 고치도록 분류만 합니다.
        """
        classes = self.config["dataset"]["classes"]
        detections = [
            {
                "class": classes[item["class_id"]],
                "confidence": round(item["confidence"], 4),
                "xyxy": [round(value, 1) for value in item["xyxy"]],
            }
            for item in row["detections"]
        ]
        prompt = (
            "첫 번째 이미지는 원본 CCTV 프레임이고 두 번째 이미지는 YOLO bbox 표시본이다. "
            "쓰레기 클래스와 bbox가 타당한지 검수하라. 쓰레기통은 검수 대상이 아니다. "
            "반드시 제공된 JSON schema만 출력하고 중국어 및 자연어 설명을 출력하지 마라. "
            f"허용 클래스: {classes}. YOLO 결과: {json.dumps(detections)}"
        )
        images = [
            base64.b64encode(Path(row["image_path"]).read_bytes()).decode("ascii"),
            base64.b64encode(Path(row["annotated_path"]).read_bytes()).decode("ascii"),
        ]
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt, "images": images}],
            "stream": False,
            "think": False,
            "format": self._review_schema(),
            "options": {"temperature": 0, "seed": SEED if "SEED" in globals() else 42},
        }
        response = self._ollama_request("POST", "/api/chat", payload)
        return self._validate_review(response["message"]["content"])

    def review(self) -> None:
        """labels.jsonl의 자동 라벨을 Qwen-VL로 검수하고 상태별 폴더로 분류합니다.

        approved는 조건을 만족하면 build에 포함될 수 있는 데이터입니다. manual_review는
        클래스나 bbox를 사람이 확인·수정해야 하므로 자동 학습에서 제외됩니다. rejected는
        흐림, 잘못된 객체 등 학습에 부적합한 데이터입니다. API 실패나 잘못된 응답도 무리하게
        승인하지 않고 재시도한 뒤 manual_review로 보내는 보수적인 정책을 사용합니다.
        전체 판단 결과는 reviews.jsonl에 남겨 검수 근거를 추적할 수 있습니다.
        """
        rows = readManifest(self.labels_manifest)
        if not rows:
            raise RuntimeError("먼저 label 단계를 실행하세요.")
        model = self._resolve_ollama_model()
        retries = int(self.config["ollama"]["retries"])
        minimum = float(self.config["ollama"]["minimum_review_confidence"])
        outputs = []

        for number, row in enumerate(rows, 1):
            review = None
            errors = []
            for attempt in range(retries + 1):
                try:
                    review = self._review_one(model, row)
                    break
                except (ValueError, RuntimeError, KeyError, json.JSONDecodeError) as error:
                    errors.append(f"attempt {attempt + 1}: {error}")
                    time.sleep(min(2 ** attempt, 5))

            if review is None:
                review = {
                    "decision": "manual_review",
                    "predicted_class": "none",
                    "issues": ["bad_bbox"],
                    "confidence": 0.0,
                }
            if review["confidence"] < minimum:
                review["decision"] = "manual_review"
            if any(issue in {
                "wrong_class", "bad_bbox", "missing_object", "extra_box", "multiple_objects"
            }
                   for issue in review["issues"]):
                review["decision"] = "manual_review"

            output = dict(row)
            output.update({"review": review, "review_errors": errors, "ollama_model": model})
            outputs.append(output)

            queue_root = {
                "approved": self.approved_root,
                "rejected": self.rejected_root,
                "manual_review": self.manual_root,
            }[review["decision"]]
            queue_dir = queue_root / row["video"]
            queue_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(row["image_path"], queue_dir / f"{row['id']}.jpg")
            shutil.copy2(row["annotated_path"], queue_dir / f"{row['id']}__annotated.jpg")
            shutil.copy2(row["label_path"], queue_dir / f"{row['id']}.txt")

            if number % 25 == 0:
                print(f"[REVIEW] {number}/{len(rows)}")

        writeManifest(self.reviews_manifest, outputs)
        counts = {name: 0 for name in ("approved", "rejected", "manual_review")}
        for row in outputs:
            counts[row["review"]["decision"]] += 1
        print(f"[REVIEW] {counts}")


def reviewLabels(pipeline: ReviewLabelsStage) -> None:
    """오케스트레이터에서 자동 검수 단계를 실행합니다."""
    pipeline.review()