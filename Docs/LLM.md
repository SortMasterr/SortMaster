# LLM.md — 모델 선택과 서빙 런타임

이 프로젝트에서 LLM을 **무엇을**, **어디에**, **어떻게 띄워서** 쓰는지 정리한 문서다.

- LLM이 파이프라인에서 맡는 **역할**과 그 역할이 축소돼 온 경위 → `Docs/ARCHITECTURE.md`의
  "LLM 활용"
- 역할 변경의 **결정 이력**(왜 좌표를 빼기로 했는지 등) → `.agentfiles/decisionLog.md`
- GPU 서버에서 **실제로 띄우고 내리는 절차** → `.agentfiles/gpuServerOps.md`의
  "vLLM(`llm` 서비스) 기동"

> **근거의 성격**: 아래 "왜 vLLM인가"는 **대안을 실제로 띄워 비교한 결과가 아니라**, 코드가
> 요구하는 조건에서 역산한 사후 정리다. vLLM은 처음부터 `docker-compose.yml`에 들어가 있었고
> 선택 이유는 어디에도 기록되지 않았던 것을, 2026-08-28에 이 분석을 근거로 정식 확정했다
> (`decisionLog.md`의 "LLM 서빙 런타임은 vLLM으로 확정"). **Ollama·llama.cpp·TGI를 실제로
> 돌려본 적은 없으므로**, 아래 비교표에서 "검증 필요"로 표시한 항목은 아직 확인되지 않은 추정이다.

## 1. 쓰는 모델

| 항목 | 값 | 어디에 정의돼 있나 |
|---|---|---|
| 모델 | `Qwen/Qwen3-VL-8B-Instruct-FP8` | `.env`의 `LLM_MODEL_NAME`, `docker-compose.yml`의 `llm` 기본값 |
| 종류 | Vision-Language (멀티모달) instruct 모델 | 이미지 2장을 한 요청에 넣어야 해서 VL 필수 |
| 크기 | 8B | 아래 "왜 8B인가" |
| 양자화 | FP8 사전양자화 | L40S(Ada Lovelace)가 FP8 네이티브 지원 |
| 파인튜닝 | **없음.** 베이스 모델 + 프롬프트만 | `decisionLog.md`, `Docs/ARCHITECTURE.md`의 "LLM 활용" |

`autoTraining/pipelineConfig.yaml`의 `qwenVl.model`은 기본값이 `auto`다 — 서버에 올라온 모델
목록(`GET /v1/models`) 중 이름에 `qwen`과 `vl`이 **둘 다** 들어간 첫 모델을 고른다
(`reviewLabels.py`의 `_resolveQwenVlModel`). 모델을 바꿔도 설정 파일을 안 고쳐도 되게 한 것이라,
서버에 Qwen-VL 계열을 두 개 이상 올리면 의도와 다른 게 잡힐 수 있다.

### 왜 8B인가

GPU 카드를 **1장(L40S 48GB)만** 배정받았고, 그 카드를 `training`(YOLO26 재학습)과 나눠 쓴다.
`Docs/ARCHITECTURE.md`의 "LLM 활용"에 적힌 대로 **32B/235B(MoE) 등 상위 사이즈는 단일 카드로
비현실적이라 배제**했다. 8B + FP8이면 아래 `--gpu-memory-utilization 0.5` 제한 안에 들어간다.

### 왜 FP8인가

L40S는 Ada Lovelace 세대라 FP8을 텐서코어에서 네이티브로 처리한다. 사전양자화 가중치를 쓰면
로딩 시점에 양자화하는 비용도 없고 VRAM도 아낀다 — 같은 카드에서 학습을 돌려야 하는 제약과
직접 이어진다.

## 2. 어떻게 띄우는가

`docker-compose.yml`의 `llm` 서비스, 이미지는 `vllm/vllm-openai:v0.27.1-cu129-ubuntu2404`.

```yaml
command:
  - --model
  - ${LLM_MODEL_NAME:-Qwen/Qwen3-VL-8B-Instruct-FP8}
  - --gpu-memory-utilization
  - "0.5"          # vLLM 기본값 0.9 → training과 VRAM을 나눠 쓰려고 낮춤(실측 후 조정 필요)
  - --max-model-len
  - "8192"
```

| 설정 | 이유 |
|---|---|
| `profiles: ["llm"]` | **상시 기동 아님.** GPU 서버가 학원 공유 자원이라 필요할 때만 켠다 |
| `NVIDIA_VISIBLE_DEVICES=${GPU_DEVICE_ID}` + `device_ids` | 베이스 이미지가 `all`을 박아둬서 명시적으로 덮어써야 **다른 팀 카드를 안 잡는다** |
| `llm-model-cache` 볼륨 | 가중치 수 GB~수십 GB 재다운로드 방지 |
| `--gpu-memory-utilization 0.5` | `training`과 같은 카드 공유 |

**온디맨드 자동 기동/종료가 구현돼 있다.** `review` 단계가 시작할 때 `llm`이 응답하지 않으면
`reviewLabels.py`가 `docker compose --profile llm up -d llm`을 직접 실행하고 준비될 때까지
기다린다(`qwenVl.startupTimeoutSeconds`, 기본 180초). 끝나면 **자기가 띄운 경우에만** 내린다 —
원래 떠 있던 컨테이너는 다른 사람이 쓰는 중일 수 있어 건드리지 않는다
(`_ensureQwenVlRunning`/`_shutdownQwenVlIfAutoStarted`).

## 3. 왜 vLLM인가

현재 코드(`autoTraining/stages/reviewLabels.py`)가 서빙 런타임에 요구하는 조건은 다섯 가지다.
각 항목은 코드나 compose에서 바로 확인할 수 있다.

### (1) 엄격한 JSON Schema 강제 — 가장 결정적

검수 요청은 스키마를 `strict: true`로 넘긴다.

```python
"response_format": {
    "type": "json_schema",
    "json_schema": {"name": "labelReview", "strict": True,
                    "schema": self._reviewSchema(len(yoloClasses))},
}
```

이 스키마의 핵심은 **`boxVerdicts` 배열 길이를 `minItems == maxItems == detectionCount`로
못박는 것**이다(`_reviewSchema`). 모델이 빈 배열로 회피하지 못하게 만드는 장치이고, 동시에
"멈추지 못하고 `max_model_len`까지 생성하는 폭주"를 **구조적으로** 막는 안전장치이기도 하다
(`pipelineConfig.yaml`의 `maxResponseTokens` 주석 참고).

즉 스키마 준수는 프롬프트로 부탁하는 게 아니라 **디코딩 단계에서 강제**돼야 한다. vLLM은
guided decoding으로 이걸 처리한다.

### (2) 멀티모달 — 한 요청에 이미지 2장

원본과 YOLO bbox가 그려진 이미지를 base64 data URL로 함께 보낸다(`reviewLabels.py`).
Qwen3-VL 같은 최신 VL 아키텍처를 서버가 지원해야 한다.

### (3) 배치 처리량

한 배치가 수천 프레임 규모다(2026-08-28 실측 배치는 **2,796건**,
`Docs/ARCHITECTURE.md`의 "LLM 활용"). 대화형 1건씩이 아니라 **대량 순회**가 본체라
연속 배칭(continuous batching)·PagedAttention 같은 처리량 최적화가 실질적 이득이 된다.

### (4) VRAM 상한을 숫자로 못박을 수 있을 것

같은 카드에서 `training`이 돌기 때문에, 런타임이 "알아서 쓰는" 게 아니라
`--gpu-memory-utilization 0.5`처럼 **사용자가 상한을 지정**할 수 있어야 한다.

### (5) OpenAI 호환 HTTP API

클라이언트가 SDK 없이 **표준 라이브러리 `urllib`만** 쓴다(`_requestQwenVl`).
`GET /v1/models`와 `POST /v1/chat/completions` 두 개면 충분하다.

부수 조건으로 `temperature: 0`, `seed: 42`를 고정해 재현성을 확보한다.

## 4. Ollama와의 비교

> **주의**: Ollama는 이 프로젝트에서 **한 번도 시도되거나 벤치마크된 적이 없다.** 아래는 위
> 요구사항에 비춘 분석이지 측정 결과가 아니다. 실제로 바꿀 생각이라면 검증이 필요하다.
> 결정 자체의 경위는 `.agentfiles/decisionLog.md` 참고.

Ollama가 못 하는 것으로 오해하기 쉬운 부분부터 정리하면 — **Ollama도 JSON Schema 기반
structured output을 지원하고, 비전 모델도 돌릴 수 있다.** 그래서 "Ollama는 JSON을 못 뽑는다"는
식의 이유는 사실이 아니다.

실제 차이는 **용도 지향점**에 있다.

| 요구사항 | vLLM | Ollama |
|---|---|---|
| (1) 엄격 스키마 | guided decoding으로 강제 | schema 지정 가능. `minItems==maxItems` 같은 제약까지 얼마나 엄격히 강제되는지는 **검증 필요** |
| (2) Qwen3-VL 지원 | 이미지 태그로 버전 고정, 최신 VL 아키텍처 대응이 빠름 | 모델 레지스트리에 올라와야 쓸 수 있어 **신규 아키텍처 반영이 늦을 수 있음(확인 필요)** |
| (3) 수천 건 배치 | 연속 배칭·PagedAttention으로 처리량 최적화 | 로컬 대화형 단일 사용자 지향. 병렬 처리 옵션은 있으나 대량 배치에 맞춘 설계는 아님 |
| (4) VRAM 상한 | `--gpu-memory-utilization`으로 명시 | 런타임이 자체 관리 — **`training`과 카드를 나눠 쓰는 이 환경에서 가장 불리한 지점** |
| (5) OpenAI 호환 API | 서버가 곧 OpenAI 호환 | 자체 API + OpenAI 호환 계층 제공 |
| 양자화 방식 | FP8 사전양자화 가중치를 그대로(Ada 네이티브) | GGUF 계열(Q4_K_M 등) 중심 — FP8 텐서코어 경로와 다름 |

**정리**: Ollama는 "노트북에서 모델 하나 빨리 띄워 써보기"에 최적화돼 있고, 이 프로젝트가 필요한
건 "공유 GPU의 정해진 몫 안에서, 수천 건을 스키마를 어기지 않고 갈아 넣는 것"이다. (3)과 (4)가
갈리는 지점이고, 특히 **(4)는 다른 팀과 카드를 공유하는 이 환경에서 타협하기 어렵다**.

반대로 vLLM의 비용도 분명하다 — **첫 기동이 느리다.** 가중치 다운로드로 수 분~수십 분이 걸려
자동 기동 타임아웃(180초)을 넘길 수 있어서, 최초 1회는 수동으로 띄워 캐시를 채워두라고
`gpuServerOps.md`에 적어뒀다. Ollama였다면 이 부분은 더 매끄러웠을 것이다.

## 5. 알려진 한계

- **`confidence`는 신뢰 신호가 아니다.** 환각에도 0.95가 붙었다
  (`decisionLog.md`, 2026-08-28). `minimumReviewConfidence`(0.70)는 보조 장치일 뿐이고 최종
  판단은 항상 사람 검수가 내린다
- **좌표를 다루지 않는다.** 정밀 로컬라이제이션은 VLM의 구조적 약점이라(IoU 중앙값 0.00)
  박스 작성은 사람 검수 UI의 드래그가 전담한다
- **파인튜닝 미착수.** 착수 조건은 이미 충족됐지만, 먼저 역할 축소로 대응했다. 다음 후보는
  ①Grounding DINO ②Qwen3-VL LoRA/QLoRA 순 — `Docs/ARCHITECTURE.md`의 "LLM 활용" 참고
- **`maxResponseTokens: 300`은 박스 15개 안팎이 한계다.** 탐지가 그보다 많은 프레임에서
  JSON이 잘리면 올려야 한다
- **모델 자동 선택(`auto`)은 Qwen-VL 계열이 둘 이상 올라오면 첫 번째를 집는다**

## 6. 아직 안 정해진 것

- `--gpu-memory-utilization 0.5`와 `--max-model-len 8192`는 **실측 없이 정한 값**이다.
  `training`과 동시 실행할 때의 실제 경합은 측정되지 않았다
- 파인튜닝 착수 여부와 방법(Unsloth / LLaMA-Factory), 배포 전 해당 사이즈의 라이선스 조항 확인
- "환경별 통 모양 인식 학습 데이터 생성"에 LLM을 쓰는 방식(미착수)
