"""4단계: Qwen-VL로 YOLO 자동 라벨을 검수하고 상태별로 분류합니다."""

import base64
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import cv2

from common.pipelineUtilities import (
    chinesePattern,
    iterateManifest,
    manifestHasRows,
)
from stages.autoLabeling import drawDetections


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

    def _isQwenVlReachable(self, timeoutSeconds: float) -> bool:
        """짧은 타임아웃으로 vLLM API 응답 여부만 확인합니다(기동 대기 폴링용)."""
        apiBaseUrl = self._resolveQwenVlApiBaseUrl()
        try:
            with urllib.request.urlopen(
                apiBaseUrl + "/v1/models",
                timeout=timeoutSeconds,
            ):
                return True
        except (urllib.error.URLError, TimeoutError):
            return False

    def _ensureQwenVlRunning(self) -> None:
        """vLLM(``llm`` 서비스)이 응답하지 않으면 온디맨드로 기동하고 준비될 때까지 대기합니다.

        GPU 서버는 팀 공유 자원이라 상시 기동 대신 review 단계를 실행할 때만 필요한
        만큼 켜는 방침(gpuServerOps.md)을 유지한다 — 이미 떠 있으면(다른 이유로
        누군가 미리 띄워둔 경우 포함) 손대지 않고, 이 실행이 직접 띄운 경우에만
        review() 종료 시 `_shutdownQwenVlIfAutoStarted`가 내린다.
        """
        if self._isQwenVlReachable(timeoutSeconds=3):
            return

        print(
            "[QWEN-VL] llm 서비스가 응답하지 않아 자동 기동합니다 "
            "(docker compose --profile llm up -d llm)"
        )
        subprocess.run(
            ["docker", "compose", "--profile", "llm", "up", "-d", "llm"],
            cwd=self.projectRoot,
            check=True,
        )
        # 여기서부터는 컨테이너가 실제로 떠 있으므로, 아래 대기가 타임아웃으로
        # 실패하더라도(RuntimeError) review()의 finally가 이 값을 보고 정리한다.
        self._qwenVlAutoStarted = True

        startupTimeoutSeconds = float(self.config["qwenVl"]["startupTimeoutSeconds"])
        deadline = time.monotonic() + startupTimeoutSeconds
        while time.monotonic() < deadline:
            if self._isQwenVlReachable(timeoutSeconds=3):
                print("[QWEN-VL] llm 서비스 기동 완료")
                return
            time.sleep(5)

        raise RuntimeError(
            "llm 서비스가 "
            f"{startupTimeoutSeconds:.0f}초 안에 응답하지 않았습니다. 첫 기동은 모델 "
            "가중치 다운로드로 더 걸릴 수 있습니다 — GPU 서버에서 "
            "`docker compose logs -f llm`으로 진행 상황을 확인하세요."
        )

    def _shutdownQwenVlIfAutoStarted(self) -> None:
        """이번 review() 실행이 직접 띄운 llm 서비스라면 끝난 뒤 내려 GPU 서버 VRAM을
        다른 팀/워크로드에 돌려준다(gpuServerOps.md). 원래부터 떠 있던 경우는
        건드리지 않는다 — 종료 실패는 원래 예외(있다면)를 가리지 않도록 로그만
        남기고 삼킨다.
        """
        if not self._qwenVlAutoStarted:
            return
        self._qwenVlAutoStarted = False

        print(
            "[QWEN-VL] review 단계가 자동으로 띄운 llm 서비스를 종료합니다 "
            "(docker compose --profile llm down)"
        )
        try:
            subprocess.run(
                ["docker", "compose", "--profile", "llm", "down"],
                cwd=self.projectRoot,
                check=True,
            )
        except (subprocess.CalledProcessError, OSError) as error:
            print(
                "[QWEN-VL] llm 서비스 자동 종료 실패 — GPU 서버에서 수동으로 "
                f"`docker compose --profile llm down`을 실행하세요: {error}"
            )

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
        maxDetections = int(self.config["qwenVl"]["maxDetectionsPerFrame"])
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
                    # 허용값이 8종뿐인데 상한이 없으면 문법상 같은 값을 무한히 반복해도
                    # 되므로, 아래 qwenDetections와 같은 이유로 원소 수를 묶는다.
                    "maxItems": 8,
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
                "qwenDetections": {
                    "type": "array",
                    # 상한이 없으면 guided decoding 문법이 배열 원소를 무한히
                    # 허용해서, 모델이 멈추지 못하고 max_model_len까지 생성하다
                    # 잘린 JSON을 내놓는 문제가 실제로 발생했다(2026-08-26). 그때는
                    # maxResponseTokens로 짧게 끊어 대응했지만, 그 상한이 객체 2개
                    # 이상인 정상 응답까지 잘라버려 Qwen 결과가 통째로 버려지는
                    # 부작용이 확인됐다(2026-08-28). 토큰 상한 대신 여기서 구조적으로
                    # 묶어야 정상 응답을 희생하지 않고 폭주만 막을 수 있다.
                    "maxItems": maxDetections,
                    "description": (
                        "Qwen이 원본 이미지에서 실제로 존재한다고 판단하는 쓰레기 "
                        "객체 목록(픽셀 좌표) — YOLO 결과와 무관하게 직접 다시 "
                        f"판단한다. 쓰레기가 없으면 빈 배열이며 최대 {maxDetections}개."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "class": {"type": "string", "enum": classes},
                            "xyxy": {
                                "type": "array",
                                "description": (
                                    "이미지 폭/높이 대비 0~1 정규화 좌표 "
                                    "[x1, y1, x2, y2] — 절대 픽셀 좌표 아님."
                                ),
                                "items": {
                                    "type": "number",
                                    "minimum": 0,
                                    "maximum": 1,
                                },
                                "minItems": 4,
                                "maxItems": 4,
                            },
                        },
                        "required": ["class", "xyxy"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": [
                "decision",
                "predictedClass",
                "issues",
                "confidence",
                "qwenDetections",
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

        classes = self.config["dataset"]["classes"]
        qwenDetections = review.get("qwenDetections")
        if not isinstance(qwenDetections, list):
            raise ValueError("qwenDetections는 배열이어야 합니다.")
        maxDetections = schema["properties"]["qwenDetections"]["maxItems"]
        if len(qwenDetections) > maxDetections:
            raise ValueError(f"qwenDetections는 최대 {maxDetections}개여야 합니다.")
        for detection in qwenDetections:
            if detection.get("class") not in classes:
                raise ValueError("qwenDetections에 허용되지 않는 class가 있습니다.")
            xyxy = detection.get("xyxy")
            if not isinstance(xyxy, list) or len(xyxy) != 4:
                raise ValueError("qwenDetections의 xyxy는 값 4개여야 합니다.")
            normalizedXyxy = [float(value) for value in xyxy]
            if not all(0.0 <= value <= 1.0 for value in normalizedXyxy):
                raise ValueError("qwenDetections의 xyxy는 0~1 정규화 좌표여야 합니다.")
            detection["xyxy"] = normalizedXyxy
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
            "YOLO bbox 표시 이미지다. 다음 두 가지를 모두 확인하라. "
            "(1) YOLO가 이미 찾은 각 객체의 클래스와 bbox가 실제로 맞는지 "
            "검증하라 — 틀렸으면 issues에 wrongClass/badBbox 등으로 표시하라. "
            "(2) YOLO 결과와 무관하게 원본 이미지를 직접 보고, YOLO가 놓친 "
            "쓰레기(허용 클래스 중 하나)가 있는지 적극적으로 확인하라 — YOLO "
            "결과가 비어 있어도 원본에 실제로 쓰레기가 있으면 그건 미탐지이므로 "
            "issues에 missingObject를 반드시 표시하고 predictedClass에 실제로 "
            "보이는 클래스를 적어라. "
            "qwenDetections에는 원본 이미지 기준으로 네가 실제로 존재한다고 "
            "판단하는 쓰레기 객체만 다시 나열하라(YOLO가 맞았어도, 놓쳤어도, "
            "틀렸어도 상관없이 네가 옳다고 보는 최종 목록) — 좌표는 절대 픽셀 "
            "값이 아니라 이미지 폭/높이에 대한 0~1 비율로 [x1,y1,x2,y2](왼쪽 "
            "위가 0,0, 오른쪽 아래가 1,1)를 적어라. 아래 YOLO 결과의 xyxy는 "
            "참고용 실제 픽셀 좌표이니 그대로 베끼지 말고 반드시 비율로 변환해서 "
            "적어라. 쓰레기가 없다고 판단하면 빈 배열로 둬라. "
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
            "max_tokens": int(self.config["qwenVl"]["maxResponseTokens"]),
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

    def _saveQwenAnnotatedImage(self, row: dict[str, Any], review: dict[str, Any]) -> Path:
        """Qwen이 직접 판단한 qwenDetections를 원본 위에 그려 사람이 눈으로
        비교할 수 있게 한다 — YOLO가 틀리게 잡은 박스는 여기서 사라지고,
        놓친 쓰레기는 여기서 새로 나타나는 식으로 확인할 수 있다."""
        classes = self.config["dataset"]["classes"]
        rawImage = cv2.imread(row["imagePath"])
        imageHeight, imageWidth = rawImage.shape[:2]
        detections = [
            {
                "classId": classes.index(detection["class"]),
                "confidence": review["confidence"],
                # Qwen은 0~1 정규화 좌표로 반환한다(모델이 내부적으로 리사이즈한
                # 크기를 알 수 없어 절대 픽셀 좌표는 신뢰할 수 없었음) — 실제
                # 이미지 크기로 환산해야 bbox가 맞는 위치에 그려진다.
                "xyxy": [
                    detection["xyxy"][0] * imageWidth,
                    detection["xyxy"][1] * imageHeight,
                    detection["xyxy"][2] * imageWidth,
                    detection["xyxy"][3] * imageHeight,
                ],
            }
            for detection in review["qwenDetections"]
        ]
        annotatedImage = drawDetections(rawImage, detections, classes)
        qwenAnnotatedPath = self.qwenAnnotatedRoot / row["video"] / f"{row['id']}.jpg"
        qwenAnnotatedPath.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(qwenAnnotatedPath), annotatedImage):
            raise OSError(f"Qwen 검수 이미지 저장 실패: {qwenAnnotatedPath}")
        return qwenAnnotatedPath

    @staticmethod
    def _appendJsonLine(path: Path, row: dict[str, Any]) -> None:
        """사람 검수 UI가 review 진행 중에도 이미 처리된 항목을 바로 볼 수 있도록,
        배치가 끝나야 파일이 나타나는 ManifestWriter의 원자적 교체 대신 한 줄씩
        즉시 append+flush한다."""
        with path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            file.flush()
            os.fsync(file.fileno())

    def review(self) -> None:
        """자동 라벨을 순차 검수하여 reviews.jsonl/humanReviewQueue.jsonl과
        상태별 폴더에 즉시 반영합니다(사람 검수 UI가 실시간으로 따라올 수 있게).

        재실행 시 중단-재개 없이 처음부터 다시 돌기 때문에, 시작 시 두 파일을
        비워서 새로 만든다.
        """
        if not manifestHasRows(self.labelsManifest):
            raise RuntimeError("먼저 label 단계를 실행하세요.")

        self._qwenVlAutoStarted = False
        try:
            self._ensureQwenVlRunning()
            self._reviewAllRows()
        finally:
            self._shutdownQwenVlIfAutoStarted()

    def _reviewAllRows(self) -> None:
        """review()의 실제 검수 루프 — llm 기동/종료 관리와 분리해, 이 루프가 도중에
        실패해도 review()의 finally가 자동 종료를 그대로 실행하게 한다."""
        qwenVlModel = self._resolveQwenVlModel()
        retries = int(self.config["qwenVl"]["retries"])
        minimumConfidence = float(
            self.config["qwenVl"]["minimumReviewConfidence"]
        )
        counts = {
            name: 0
            for name in ("approved", "rejected", "manualReview")
        }

        self.reviewsManifest.parent.mkdir(parents=True, exist_ok=True)
        self.humanReviewQueue.parent.mkdir(parents=True, exist_ok=True)
        self.reviewsManifest.write_text("", encoding="utf-8")
        self.humanReviewQueue.write_text("", encoding="utf-8")

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
                    "qwenDetections": [],
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

            qwenAnnotatedPath = self._saveQwenAnnotatedImage(row, review)

            output = dict(row)
            output.update({
                "review": review,
                "reviewErrors": errors,
                "qwenVlModel": qwenVlModel,
                "qwenAnnotatedPath": str(qwenAnnotatedPath.resolve()),
            })
            self._appendJsonLine(self.reviewsManifest, output)

            # exportHumanReviewQueue()가 하던 변환을 여기서 바로 적용해, 사람
            # 검수 큐도 review와 같은 속도로 실시간 성장한다.
            queueRow = dict(output)
            queueRow["batchId"] = self.batchId
            queueRow["humanDecision"] = None
            self._appendJsonLine(self.humanReviewQueue, queueRow)

            counts[review["decision"]] += 1

            # 배치가 다 끝나야만 결과를 볼 수 있으면 중간에 이상한 값이 나와도
            # 늦게 알게 되므로, 프레임마다 핵심 판정을 바로 찍는다.
            print(
                f"[REVIEW] {row['id']} -> {review['decision']} "
                f"class={review['predictedClass']} "
                f"issues={review['issues']} "
                f"confidence={review['confidence']:.2f} "
                f"qwenBoxes={len(review['qwenDetections'])}"
            )

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
                qwenAnnotatedPath,
                queueDirectory / f"{row['id']}__qwen.jpg",
            )
            shutil.copy2(
                row["labelPath"],
                queueDirectory / f"{row['id']}.txt",
            )

        print(f"[REVIEW] {counts}")


def reviewLabels(pipeline: ReviewLabelsStage) -> None:
    """오케스트레이터에서 Qwen-VL 검수 단계를 실행합니다.

    review()가 이제 humanReviewQueue.jsonl까지 프레임마다 바로 채우므로(사람
    검수 UI 실시간 반영), 배치 전체가 끝난 뒤 다시 훑는 별도
    exportHumanReviewQueue() 호출은 더 이상 필요 없다 — Qwen의 approved/rejected도
    오판할 수 있어 모든 결과를 사람 검수로 보내는 정책 자체는 review()의
    queueRow 구성에 그대로 남아 있다.
    """
    pipeline.review()
