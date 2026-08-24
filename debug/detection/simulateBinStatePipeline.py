"""외부 넘침 감지 모델 대신 BIN_STATES 상태 갱신 신호(NORMAL→FULL→NORMAL)를 흉내내서
binStateService의 전환 판정 → overflow EVENT 생성/복귀 파이프라인을 로컬에서 검증하는
디버그 스크립트. simulateEventPipeline.py와 같은 성격(백엔드 코드 변경 없이 로컬 검증
전용)이며 실제 HTTP API(POST /api/binStates)가 호출하는 서비스와 동일한 진입점을 쓴다.

실행(반드시 프로젝트 루트에서, backend venv 활성화 후):
    python debug/detection/simulateBinStatePipeline.py

MongoDB(.env의 MONGO_HOST/DB_PORT 등)가 준비되어 있어야 함.
"""
import asyncio
import os
import sys
from uuid import uuid4

from dotenv import load_dotenv

_scriptDir = os.path.dirname(os.path.abspath(__file__))
_backendDir = os.path.join(
    _scriptDir, "..", "..", "WebApps", "backend"
)
_projectRootEnv = os.path.join(
    _scriptDir, "..", "..", ".env"
)

sys.path.insert(0, _backendDir)
load_dotenv(_projectRootEnv)

fullDurationSeconds = 3  # FULL 상태로 관측되는 임의 구간(시연용)


async def main() -> None:
    # motor 클라이언트는 생성 시점의 실행 중인 이벤트 루프에 바인딩되므로, 파일 최상단이
    # 아니라 asyncio.run()이 만든 루프 안에서 지연 import한다(simulateEventPipeline.py와
    # 동일한 이유).
    from schemas.binState import BinCurrentState, BinStateUpdate
    from schemas.event import BinType
    from services.binStateService import binStateService

    binId = "BIN-GENERAL"
    sessionId = str(uuid4())

    print(f"[시뮬레이션] '{binId}' NORMAL→FULL 전환 신호 전송")
    binState, eventResult = await binStateService.applyUpdate(
        BinStateUpdate(
            binId=binId,
            binType=BinType.GENERAL,
            sessionId=sessionId,
            currentState=BinCurrentState.FULL,
            confidenceScore=0.97,
            overflowDuration=0.0,
            overflowThreshold=5.0,
            detectionId=str(uuid4()),
            modelVersion="overflow-dev",
        )
    )

    if eventResult is not None and eventResult.created:
        print(
            f"[시뮬레이션] overflow 이벤트 생성됨: "
            f"eventId={eventResult.event.eventId}, "
            f"activeOverflowEventId={binState.activeOverflowEventId}"
        )
    else:
        print(
            "[시뮬레이션] 이미 FULL 상태였거나 중복 detectionId라 "
            "새 이벤트가 생성되지 않았습니다."
        )

    print(
        f"[시뮬레이션] {fullDurationSeconds}초 동안 FULL 유지 상태를 "
        "보고(전환 없음, EVENT 재생성 안 함)..."
    )
    await asyncio.sleep(fullDurationSeconds)
    binState, eventResult = await binStateService.applyUpdate(
        BinStateUpdate(
            binId=binId,
            binType=BinType.GENERAL,
            sessionId=sessionId,
            currentState=BinCurrentState.FULL,
            confidenceScore=0.98,
            overflowDuration=float(fullDurationSeconds),
            overflowThreshold=5.0,
            detectionId=str(uuid4()),
            modelVersion="overflow-dev",
        )
    )
    assert eventResult is None, "FULL 유지 중엔 EVENT가 다시 생기면 안 됨"

    print(f"[시뮬레이션] '{binId}' FULL→NORMAL 복귀 신호 전송")
    binState, eventResult = await binStateService.applyUpdate(
        BinStateUpdate(
            binId=binId,
            binType=BinType.GENERAL,
            sessionId=sessionId,
            currentState=BinCurrentState.NORMAL,
            confidenceScore=0.95,
            overflowDuration=0.0,
            overflowThreshold=5.0,
            detectionId=str(uuid4()),
            modelVersion="overflow-dev",
        )
    )

    print(
        f"[시뮬레이션] 최종 상태: currentState={binState.currentState.value}, "
        f"activeOverflowEventId={binState.activeOverflowEventId}"
    )


if __name__ == "__main__":
    asyncio.run(main())
