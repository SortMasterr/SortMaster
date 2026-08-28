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

from common.pipelineUtilities import (
    chinesePattern,
    iterateManifest,
    manifestHasRows,
)

# 박스 안에 쓰레기가 아예 없다(YOLO 오탐)는 뜻으로 모델이 고를 수 있는 값.
# dataset.classes와 섞이지 않도록 별도 상수로 둔다.
notTrashClass = "notTrash"


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

    def _reviewSchema(self, detectionCount: int) -> dict[str, Any]:
        """Qwen-VL이 반환해야 하는 camelCase JSON 구조를 정의합니다.

        **모델에게는 "박스별 닫힌 검증"만 시킨다.** YOLO가 그린 박스마다 그 안에 실제로
        무엇이 있는지 하나씩 답하게 하고(`boxVerdicts`), 배열 길이를 탐지 개수에 정확히
        고정해(`minItems == maxItems == detectionCount`) 빈 배열로 회피할 수 없게 한다.

        이 구조에 이르기까지의 경위(2026-08-28 실측):
        - 좌표(bbox)를 요구했더니 없는 물체를 confidence 0.95로 만들어내는 환각이 나왔다.
          정밀 로컬라이제이션은 VLM의 구조적 약점이라 좌표는 아예 받지 않는다.
        - 그다음 프레임 단위 `decision`/`predictedClass` 하나만 받도록 축소했더니 2,796건
          전부 `predictedClass=none`, `issues=[]`로 동일한 무의미 출력이 나왔다. 원인은
          (a) 프레임에 박스가 여럿인데 클래스 필드가 하나뿐이라 "1번은 맞고 2번은 틀렸다"를
          표현할 수 없었고, (b) `decision`/`none`이 모델에게 판단 보류라는 탈출구를 준 것.
          `decision`은 어차피 아래 `review()`가 신뢰도·이슈로 다시 계산하므로 제거했다.
        - 별도 실측에서 모델이 이미지를 정확히 묘사하는 것은 확인됐고(인지 능력은 충분),
          같은 프롬프트를 스키마 없이 물었을 때와 답이 일치해 guided decoding 자체는
          원인이 아니었다.

        `issues`와 `decision`은 모델에게 묻지 않고 `review()`가 YOLO 라벨과 이 응답을
        비교해 직접 도출한다.
        """
        classes = self.config["dataset"]["classes"]
        return {
            "type": "object",
            "properties": {
                "boxVerdicts": {
                    "type": "array",
                    "description": (
                        "YOLO 박스와 같은 순서·같은 개수로, 각 박스 안에 실제로 있는 것."
                    ),
                    "minItems": detectionCount,
                    "maxItems": detectionCount,
                    "items": {
                        "type": "object",
                        "properties": {
                            "actualClass": {
                                "type": "string",
                                "enum": classes + [notTrashClass],
                            },
                        },
                        "required": ["actualClass"],
                        "additionalProperties": False,
                    },
                },
                "hasMissedTrash": {
                    "type": "boolean",
                    "description": "YOLO가 잡지 못한 쓰레기가 원본에 있으면 true.",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
            },
            "required": ["boxVerdicts", "hasMissedTrash", "confidence"],
            "additionalProperties": False,
        }

    def _validateReview(self, content: str, detectionCount: int) -> dict[str, Any]:
        """Qwen-VL 응답의 JSON 형식과 허용값을 후속 처리 전에 검증합니다."""
        if chinesePattern.search(content):
            raise ValueError("Qwen-VL 응답에 허용하지 않는 중국어 문자가 있습니다.")

        review = json.loads(content)
        schema = self._reviewSchema(detectionCount)
        allowedClasses = set(
            schema["properties"]["boxVerdicts"]["items"]["properties"]["actualClass"]["enum"]
        )

        verdicts = review.get("boxVerdicts")
        if not isinstance(verdicts, list):
            raise ValueError("boxVerdicts는 배열이어야 합니다.")
        # 길이가 어긋나면 어느 판정이 어느 박스인지 알 수 없으므로 응답 전체를 버린다.
        if len(verdicts) != detectionCount:
            raise ValueError(
                f"boxVerdicts는 YOLO 탐지 개수({detectionCount})와 같아야 합니다: {len(verdicts)}"
            )
        for verdict in verdicts:
            if verdict.get("actualClass") not in allowedClasses:
                raise ValueError("boxVerdicts에 허용되지 않는 actualClass가 있습니다.")

        if not isinstance(review.get("hasMissedTrash"), bool):
            raise ValueError("hasMissedTrash는 불리언이어야 합니다.")

        confidence = float(review.get("confidence", -1))
        if not 0 <= confidence <= 1:
            raise ValueError("confidence는 0과 1 사이여야 합니다.")
        review["confidence"] = confidence
        return review

    def _yoloClasses(self, row: dict[str, Any]) -> list[str]:
        """한 프레임의 YOLO 탐지를 클래스명 리스트로 바꿉니다(박스 순서 유지)."""
        classes = self.config["dataset"]["classes"]
        return [classes[item["classId"]] for item in row["detections"]]

    @staticmethod
    def _deriveIssues(
        yoloClasses: list[str],
        review: dict[str, Any],
    ) -> tuple[list[str], list[dict[str, str]]]:
        """모델의 박스별 판정을 YOLO 라벨과 대조해 기존 `issues` 어휘로 옮깁니다.

        모델에게 `issues`를 직접 묻지 않는 이유는 `_reviewSchema` 참고 — 판단 보류
        탈출구를 주지 않으려고 닫힌 질문만 하고, 해석은 이쪽에서 한다. 사람 검수 UI가
        바로 쓸 수 있도록 YOLO와 모델 답을 나란히 둔 비교표도 같이 만든다.
        """
        verdicts = [verdict["actualClass"] for verdict in review["boxVerdicts"]]
        comparison = [
            {"yolo": yoloClass, "qwen": verdict}
            for yoloClass, verdict in zip(yoloClasses, verdicts)
        ]
        issues = []
        if any(verdict == notTrashClass for verdict in verdicts):
            issues.append("extraBox")
        if any(
            verdict != notTrashClass and verdict != yoloClass
            for yoloClass, verdict in zip(yoloClasses, verdicts)
        ):
            issues.append("wrongClass")
        if review["hasMissedTrash"]:
            issues.append("missingObject")
        return (issues or ["none"]), comparison

    def _reviewOne(
        self,
        qwenVlModel: str,
        row: dict[str, Any],
    ) -> dict[str, Any]:
        """원본과 bbox 표시 이미지를 Qwen-VL에 보내 한 프레임을 검수합니다."""
        yoloClasses = self._yoloClasses(row)
        # "이 프레임에 뭐가 있나"(열린 생성)가 아니라 "이 박스가 맞나"(닫힌 검증)를 묻는다 —
        # VLM은 생성보다 검증을 잘하고, 열린 질문으로 물었을 때는 전 프레임이 같은 답으로
        # 무너졌다(2026-08-28, 자세한 경위는 _reviewSchema 참고).
        prompt = (
            "첫 번째 이미지는 원본 CCTV 프레임이고, 두 번째 이미지는 YOLO가 찾은 박스를 "
            "그려 넣은 같은 프레임이다. YOLO가 잡은 박스 목록은 아래 순서와 같다. "
            "각 박스마다 그 안에 실제로 무엇이 있는지 보고 actualClass를 정하라 — "
            "YOLO 라벨이 맞으면 같은 값을, 틀렸으면 올바른 클래스를, 애초에 쓰레기가 "
            f"아니면 {notTrashClass}를 적어라. 반드시 박스 개수만큼 같은 순서로 답하라. "
            "또 원본 이미지에서 YOLO가 아예 놓친 쓰레기가 보이면 hasMissedTrash를 "
            "true로 하라. 확실히 보이는 것만 근거로 판단하고, 없는 물체를 추측해서 "
            "만들어내지 마라. 위치나 좌표는 답하지 않는다(박스 작성은 사람이 한다). "
            "쓰레기통 자체는 검수 대상이 아니다. 반드시 제공된 JSON schema만 "
            "출력하고 중국어와 자연어 설명은 출력하지 마라. "
            f"허용 클래스: {self.config['dataset']['classes']}. "
            f"YOLO 박스 순서: {json.dumps(yoloClasses, ensure_ascii=False)}"
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
                    "schema": self._reviewSchema(len(yoloClasses)),
                },
            },
        }
        response = self._requestQwenVl("POST", "/v1/chat/completions", payload)
        return self._validateReview(
            response["choices"][0]["message"]["content"],
            len(yoloClasses),
        )

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
                    "boxVerdicts": [],
                    "hasMissedTrash": False,
                    "confidence": 0.0,
                    "issues": ["badBbox"],
                    "boxComparison": [],
                }
            else:
                # issues/decision은 모델이 아니라 여기서 도출한다(_reviewSchema 참고).
                issues, comparison = self._deriveIssues(self._yoloClasses(row), review)
                review["issues"] = issues
                review["boxComparison"] = comparison

            riskyIssues = {
                "wrongClass",
                "badBbox",
                "missingObject",
                "extraBox",
                "multipleObjects",
            }
            hasRiskyIssue = any(issue in riskyIssues for issue in review["issues"])
            review["decision"] = (
                "manualReview"
                if review["confidence"] < minimumConfidence or hasRiskyIssue
                else "approved"
            )

            output = dict(row)
            output.update({
                "review": review,
                "reviewErrors": errors,
                "qwenVlModel": qwenVlModel,
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
            boxSummary = ", ".join(
                item["yolo"] if item["yolo"] == item["qwen"]
                else f"{item['yolo']}->{item['qwen']}"
                for item in review["boxComparison"]
            ) or "(박스 없음)"
            print(
                f"[REVIEW] {row['id']} -> {review['decision']} "
                f"boxes=[{boxSummary}] "
                f"missed={review['hasMissedTrash']} "
                f"issues={review['issues']} "
                f"confidence={review['confidence']:.2f}"
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
