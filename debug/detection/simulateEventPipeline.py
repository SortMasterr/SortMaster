"""
탐지 서비스(services/detectionService.py) 도착 전, "이벤트 시작"/"이벤트 종료" 두 신호를
흉내내서 녹화→GIF 인코딩→GridFS 업로드→이벤트 저장까지 전체 파이프라인을 로컬에서 검증하는
디버그 스크립트. debug/streaming/startRtspSim.py와 같은 성격(백엔드 코드 변경 없이 로컬
검증 전용)이지만, 이번엔 백엔드 서비스 모듈을 직접 import해서 실제 흐름 그대로 호출한다.

향후 detectionService.py가 생기면, 여기서 하는 것과 동일하게:
  이벤트 시작 감지 → recordingService.start(cameraId)
  이벤트 종료 감지 → recordingService.stop(recordingId) → mediaService.saveClipAsGif(...)
                    → eventService.createEvent(...)
순서로 직접 호출하면 된다(고정 10초가 아니라 시작~종료 실제 구간만큼 녹화됨).

실행(반드시 프로젝트 루트에서, backend venv 활성화 후):
    python debug/detection/simulateEventPipeline.py

MongoDB(.env의 MONGO_HOST/DB_PORT 등)와 카메라(.env의 CAMERA_SOURCE_ELEV01, 미설정 시
기본값 0=로컬 웹캠)가 준비되어 있어야 함.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

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
        CameraId,
        DetectedClass,
        EventCategory,
        EventCreate,
    )
    from services.eventService import eventService
    from services.mediaService import mediaService
    from services.recordingService import (
        recordingService,
    )

    cameraId = CameraId.ELEV01

    print(
        f"[시뮬레이션] '{cameraId.value}' 이벤트 시작 신호 → 녹화 시작"
    )
    recordingId = await recordingService.start(cameraId)

    print(
        f"[시뮬레이션] {watchSeconds}초 동안 관찰 중"
        "(실제로는 AI가 종료를 감지할 때까지의 구간)..."
    )
    await asyncio.sleep(watchSeconds)

    print("[시뮬레이션] 이벤트 종료 신호 → 녹화 종료")
    frames, durationSeconds = await recordingService.stop(
        recordingId
    )
    print(
        f"[시뮬레이션] 캡처된 프레임 수: {len(frames)}, "
        f"실제 녹화 구간: {durationSeconds:.1f}초"
    )

    timestamp = datetime.now(timezone.utc)
    imageFileId = await mediaService.saveClipAsGif(
        frames, cameraId, timestamp
    )
    print(
        f"[시뮬레이션] GIF GridFS 업로드 완료: "
        f"imageFileId={imageFileId}"
    )

    eventCreate = EventCreate(
        cameraId=cameraId,
        eventCategory=EventCategory.MISCLASSIFICATION,
        detectedClass=DetectedClass.PLASTIC,
        isMisclassified=True,
        confidenceScore=0.93,
        imageFileId=imageFileId,
    )
    event = await eventService.createEvent(eventCreate)

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
