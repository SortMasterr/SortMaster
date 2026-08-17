"""
외부 모델 대신 "이벤트 시작"/"이벤트 종료" 두 신호를 흉내내서 detectionService의
녹화→GIF 인코딩→GridFS 업로드→이벤트 저장 전체 파이프라인을 로컬에서 검증하는
디버그 스크립트. debug/streaming/startRtspSim.py와 같은 성격(백엔드 코드 변경 없이 로컬
검증 전용)이며 실제 HTTP API가 호출하는 서비스와 동일한 진입점을 사용한다.

실행(반드시 프로젝트 루트에서, backend venv 활성화 후):
    python debug/detection/simulateEventPipeline.py

MongoDB(.env의 MONGO_HOST/DB_PORT 등)와 카메라(.env의 CAMERA_SOURCE_ELEVTOP, 미설정 시
기본값 0=로컬 웹캠)가 준비되어 있어야 함.
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

watchSeconds = 4  # AI가 이벤트를 관찰 중이라고 가정하는 임의 구간(시작~종료 사이)


async def main() -> None:
    # motor(AsyncIOMotorClient)는 생성 시점의 실행 중인 이벤트 루프에 바인딩되므로,
    # 모듈 import(그중 repositories/mongoClient.py의 클라이언트 생성)를 asyncio.run()이
    # 만든 루프 "안에서" 지연 실행해야 함 — 파일 최상단에서 import하면 아직 루프가 없는
    # 상태에서 바인딩돼 "Future attached to a different loop" 에러가 남.
    from schemas.event import (
        BinType,
        CameraId,
        DetectedClass,
        EventCategory,
    )
    from services.detectionService import (
        detectionService,
    )

    cameraId = CameraId.ELEVTOP

    print(
        f"[시뮬레이션] '{cameraId.value}' 이벤트 시작 신호 → 녹화 시작"
    )
    recordingId = await detectionService.startDetection(cameraId)

    print(
        f"[시뮬레이션] {watchSeconds}초 동안 관찰 중"
        "(실제로는 AI가 종료를 감지할 때까지의 구간)..."
    )
    await asyncio.sleep(watchSeconds)

    print("[시뮬레이션] 이벤트 종료 신호 → 녹화 종료")
    event = await detectionService.stopDetection(
        recordingId=recordingId,
        cameraId=cameraId,
        eventCategory=EventCategory.MISCLASSIFICATION,
        detectionId=str(uuid4()),
        trackingId=1,
        detectedClass=DetectedClass.PLASTIC,
        binId="BIN-PAPER",
        binType=BinType.PAPER,
        isMisclassified=True,
        confidenceScore=0.93,
        overflowDuration=None,
        overflowThreshold=None,
        modelVersion="yolo26-dev",
    )

    if event is None:
        print(
            "[시뮬레이션] 쿨다운 등으로 이벤트가 저장되지 "
            "않았습니다(None 반환)."
        )
    else:
        print(
            f"[시뮬레이션] 이벤트 저장 완료: "
            f"eventId={event.eventId}, "
            f"imageFileId={event.imageFileId}"
        )


if __name__ == "__main__":
    asyncio.run(main())
