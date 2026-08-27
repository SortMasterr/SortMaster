import asyncio
from datetime import datetime, timezone

from bson.errors import InvalidId
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)
from fastapi.responses import Response, StreamingResponse

from schemas.aiDisposalEvent import AiDisposalEvent
from schemas.binState import BinState, BinStateUpdate
from schemas.detection import (
    DetectionStart,
    DetectionStartResponse,
    DetectionStop,
)
from schemas.event import (
    CameraId,
    Event,
    EventCategory,
    EventCreate,
)
from schemas.gpuHeartbeat import GpuHeartbeatPing, GpuHeartbeatStatus
from schemas.mode import (
    Mode,
    ModeResponse,
    ModeUpdate,
)
from schemas.report import (
    ReportEmailSettingsRequest,
    ReportEmailSettingsResponse,
)
from schemas.statistics import Statistics
from schemas.collectionTask import (
    CollectionAutomationStatus,
    CollectionTask,
    CollectionTaskList,
    CollectionTaskStatus,
)
from schemas.visitClip import TrackEndedRequest, TrackStartedRequest, VisitClipSummary
from services.binStateService import binStateService
from services.collectionTaskService import (
    CollectionTaskConflictError,
    CollectionTaskNotFoundError,
    collectionTaskService,
)
from services.detectionService import detectionService
from services.errors import (
    CameraUnavailableError,
    EmptyRecordingError,
    RecordingCameraMismatchError,
    RecordingConflictError,
    RecordingNotFoundError,
    ReportEmailSettingsError,
)
from services.eventService import eventService
from services.gpuHeartbeatService import gpuHeartbeatService
from services.mediaService import mediaService
from services.modeService import modeService
from services.reportEmailService import reportEmailService
from services.visitClipService import visitClipService
from services.webSocketManager import (
    webSocketManager,
)
from streaming.cameraManager import (
    cameraManagers,
)


router = APIRouter(
    prefix="/api",
    tags=["events"],
)


@router.post(
    "/reports/email",
    response_model=ReportEmailSettingsResponse,
    responses={
        422: {"description": "이메일 형식 오류"},
        500: {"description": "이메일 설정 저장 실패"},
    },
)
def saveReportEmailSettings(
    request: ReportEmailSettingsRequest,
) -> ReportEmailSettingsResponse:
    try:
        return reportEmailService.saveSettings(request)
    except ReportEmailSettingsError as error:
        raise HTTPException(
            status_code=500,
            detail="자동 보고서 수신 이메일을 저장할 수 없습니다.",
        ) from error


@router.get(
    "/reports/email",
    response_model=ReportEmailSettingsResponse,
    responses={500: {"description": "이메일 설정 조회 실패"}},
)
def getReportEmailSettings() -> ReportEmailSettingsResponse:
    try:
        return reportEmailService.getSettings()
    except ReportEmailSettingsError as error:
        raise HTTPException(
            status_code=500,
            detail="자동 보고서 수신 이메일을 불러올 수 없습니다.",
        ) from error


@router.get(
    "/events",
    response_model=list[Event],
)
async def getEvents(
    fromDate: datetime | None = Query(
        default=None,
        alias="from",
    ),
    toDate: datetime | None = Query(
        default=None,
        alias="to",
    ),
) -> list[Event]:
    return await eventService.getEvents(
        fromDate=fromDate,
        toDate=toDate,
    )


@router.get(
    "/events/{id}",
    response_model=Event,
)
async def getEventById(
    id: str,
) -> Event:
    event = await eventService.getEventById(
        id
    )

    if event is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "이벤트를 찾을 수 없습니다."
            ),
        )

    return event


@router.get(
    "/events/{id}/media",
    response_class=Response,
    responses={
        404: {"description": "이벤트 또는 저장된 GIF를 찾을 수 없음"},
    },
)
async def getEventMedia(
    id: str,
) -> Response:
    event = await eventService.getEventById(id)

    if event is None or event.imageFileId is None:
        raise HTTPException(
            status_code=404,
            detail="저장된 이벤트 GIF가 없습니다.",
        )

    clipBytes = await mediaService.getClip(
        event.imageFileId,
        event.cameraId,
    )

    if clipBytes is None:
        raise HTTPException(
            status_code=404,
            detail="저장된 이벤트 GIF를 찾을 수 없습니다.",
        )

    return Response(
        content=clipBytes,
        media_type="image/gif",
        headers={
            "Cache-Control": "private, max-age=300",
        },
    )


@router.post(
    "/events",
    response_model=Event | None,
)
async def createEvent(
    eventCreate: EventCreate,
) -> Event | None:
    creationResult = (
        await eventService.createEventWithStatus(
            eventCreate
        )
    )

    if creationResult.created:
        await _broadcastIfManageMode(
            creationResult.event
        )

    return creationResult.event


@router.post(
    "/events/aiDisposal",
    response_model=Event | None,
)
async def createEventFromAiDisposal(
    aiEvent: AiDisposalEvent,
) -> Event | None:
    """GPU 서버의 models/trashdetect/tracking2.py가 투척 완료 시 직접 POST하는 엔드포인트.

    presenceGateService가 관리하는 recordingId 기반 흐름(/detection/start,stop)과는
    독립적 — tracking2.py가 자체적으로 영상을 보고 투척 완료를 판단해서 이 엔드포인트로
    푸시하는 구조(우리가 프레임을 보내는 게 아니라 저쪽이 결과를 보내옴).
    """
    creationResult = (
        await eventService.createEventFromAiDisposal(
            aiEvent
        )
    )

    if creationResult.created:
        await _broadcastIfManageMode(
            creationResult.event
        )

    return creationResult.event


@router.post(
    "/events/trackStarted",
    status_code=200,
)
async def trackStarted(
    request: TrackStartedRequest,
) -> None:
    """GPU가 새 트랙을 발견하는 즉시 보내는 경량 신호(EP-14, 설계는 architecture.md
    "재학습용 미확정 방문 캡처" 참고). presence 기반 방문 녹화(visitClip)와 시간으로
    1차 연결하기 위한 메모리 저장 — DB 저장이나 이벤트 생성은 하지 않는다.
    """
    visitClipService.recordTrackStarted(
        request.trackId,
        request.cameraId,
        request.timestamp,
    )


@router.post(
    "/events/trackEnded",
    status_code=200,
)
async def trackEnded(
    request: TrackEndedRequest,
) -> None:
    """GPU가 트랙을 확정 못 하고 놓쳤을 때(aiDisposal 대신) 보내는 신호(EP-15).

    해당 트랙이 속한 visitClip을 재학습 후보(미확정 방문)로 표시한다.
    """
    await visitClipService.registerTrackEnded(request.trackId)


@router.get(
    "/visitClips",
    response_model=list[VisitClipSummary],
)
async def listVisitClips(
    limit: int = Query(default=60, ge=1, le=200),
) -> list[VisitClipSummary]:
    """관리자 웹에서 방문(재학습 후보 포함) 클립을 최신순으로 훑어보기 위한 목록."""
    return await visitClipService.listRecentClips(limit)


@router.get(
    "/visitClips/{clipId}/media",
)
async def getVisitClipMedia(
    clipId: str,
) -> Response:
    try:
        mediaBytes = await visitClipService.getClipMediaBytes(clipId)
    except (ValueError, InvalidId) as error:
        raise HTTPException(status_code=404, detail="잘못된 클립 ID입니다.") from error
    if mediaBytes is None:
        raise HTTPException(status_code=404, detail="클립을 찾을 수 없습니다.")
    return Response(content=mediaBytes, media_type="image/gif")


async def _broadcastIfManageMode(
    event: Event | None,
) -> None:
    currentMode = modeService.getMode().mode

    if event is None or currentMode != Mode.manage:
        return

    if (
        event.eventCategory
        == EventCategory.MISCLASSIFICATION
    ):
        payload = {
            "eventType": (
                "MISCLASSIFICATION_DETECTED"
            ),
            "cameraId": event.cameraId.value,
            "timestamp": (
                event.timestamp.isoformat()
            ),
            "isMisclassified": (
                event.isMisclassified
            ),
        }
    else:
        payload = {
            "eventType": (
                "BIN_OVERFLOW_DETECTED"
            ),
            "cameraId": event.cameraId.value,
            "timestamp": (
                event.timestamp.isoformat()
            ),
        }

    await webSocketManager.broadcast(payload)


@router.post(
    "/detection/start",
    response_model=DetectionStartResponse,
)
async def startDetection(
    detectionStart: DetectionStart,
) -> DetectionStartResponse:
    try:
        recordingId = (
            await detectionService.startDetection(
                detectionStart.cameraId
            )
        )
    except CameraUnavailableError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    return DetectionStartResponse(
        recordingId=recordingId
    )


@router.post(
    "/detection/stop",
    response_model=Event | None,
)
async def stopDetection(
    detectionStop: DetectionStop,
) -> Event | None:
    try:
        creationResult = (
            await detectionService.stopDetectionWithStatus(
                recordingId=detectionStop.recordingId,
                cameraId=detectionStop.cameraId,
                eventCategory=detectionStop.eventCategory,
                detectionId=detectionStop.detectionId,
                trackingId=detectionStop.trackingId,
                detectedClass=detectionStop.detectedClass,
                binId=detectionStop.binId,
                binType=detectionStop.binType,
                isMisclassified=detectionStop.isMisclassified,
                confidenceScore=detectionStop.confidenceScore,
                overflowDuration=detectionStop.overflowDuration,
                overflowThreshold=detectionStop.overflowThreshold,
                modelVersion=detectionStop.modelVersion,
            )
        )
    except RecordingNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error
    except (
        EmptyRecordingError,
        RecordingCameraMismatchError,
        RecordingConflictError,
    ) as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    if creationResult.created:
        await _broadcastIfManageMode(
            creationResult.event
        )

    return creationResult.event


@router.get(
    "/statistics",
    response_model=Statistics,
)
async def getStatistics(
    fromDate: datetime | None = Query(
        default=None,
        alias="from",
    ),
    toDate: datetime | None = Query(
        default=None,
        alias="to",
    ),
) -> Statistics:
    return await eventService.getStatistics(
        fromDate=fromDate,
        toDate=toDate,
    )


@router.get(
    "/binStates",
    response_model=list[BinState],
)
async def getBinStates() -> list[BinState]:
    return await binStateService.getBinStates()


@router.post(
    "/binStates",
    response_model=BinState,
)
async def updateBinState(
    binStateUpdate: BinStateUpdate,
) -> BinState:
    (
        binState,
        eventResult,
    ) = await binStateService.applyUpdate(
        binStateUpdate
    )

    if eventResult is not None and eventResult.created:
        await _broadcastIfManageMode(
            eventResult.event
        )

    return binState


@router.get(
    "/gpuHeartbeats",
    response_model=list[GpuHeartbeatStatus],
)
async def getGpuHeartbeats() -> list[GpuHeartbeatStatus]:
    return await gpuHeartbeatService.getStatuses()


@router.post(
    "/gpuHeartbeats",
    response_model=GpuHeartbeatStatus,
)
async def recordGpuHeartbeat(
    ping: GpuHeartbeatPing,
) -> GpuHeartbeatStatus:
    return await gpuHeartbeatService.recordHeartbeat(ping.cameraId)


@router.get(
    "/collectionTasks",
    response_model=CollectionTaskList,
)
async def getCollectionTasks(
    taskStatus: CollectionTaskStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> CollectionTaskList:
    return await collectionTaskService.getTasks(taskStatus, limit)


@router.post(
    "/collectionTasks/{collectionTaskId}/acknowledge",
    response_model=CollectionTask,
)
async def acknowledgeCollectionTask(
    collectionTaskId: str,
) -> CollectionTask:
    try:
        return await collectionTaskService.acknowledge(collectionTaskId)
    except CollectionTaskNotFoundError as error:
        raise HTTPException(status_code=404, detail="수거 작업을 찾을 수 없습니다.") from error
    except CollectionTaskConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/collectionTasks/{collectionTaskId}/complete",
    response_model=CollectionTask,
)
async def completeCollectionTask(
    collectionTaskId: str,
) -> CollectionTask:
    try:
        return await collectionTaskService.complete(collectionTaskId)
    except CollectionTaskNotFoundError as error:
        raise HTTPException(status_code=404, detail="수거 작업을 찾을 수 없습니다.") from error
    except CollectionTaskConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get(
    "/collectionAutomation/status",
    response_model=CollectionAutomationStatus,
)
async def getCollectionAutomationStatus() -> CollectionAutomationStatus:
    return await collectionTaskService.getAutomationStatus()


@router.post(
    "/mode",
    response_model=ModeResponse,
)
async def updateMode(
    modeUpdate: ModeUpdate,
) -> ModeResponse:
    modeResponse = (
        modeService.updateMode(
            modeUpdate
        )
    )

    await webSocketManager.broadcast(
        {
            "eventType": "MODE_CHANGED",
            "mode": (
                modeResponse.mode.value
            ),
            "timestamp": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }
    )

    return modeResponse


async def generateMjpegFrames(
    cameraManager,
):
    lastFrame = None

    while True:
        frame = (
            await cameraManager.readFrame()
        )

        # readFrame()이 캐시된 최신 프레임을 즉시 반환하는 논블로킹 방식이라,
        # 아무 제한 없이 그냥 계속 yield하면 프레임이 안 바뀐 사이에도 초당
        # 수천 번씩 같은 프레임을 재전송하게 됨 — 그 중복 전송이 네트워크 큐를
        # 채워서 실제 최신 프레임 도착이 오히려 늦어지는 지연을 만듦(실사용 중
        # 확인됨). 그래서 실제로 바뀐 프레임만 전송한다(is 비교 — 새 프레임마다
        # cameraManager 쪽에서 새 bytes 객체를 만들어서 저장하므로 충분).
        if frame is None or frame is lastFrame:
            await asyncio.sleep(0.03)
            continue

        lastFrame = frame

        yield (
            b"--frame\r\n"
            b"Content-Type: "
            b"image/jpeg\r\n\r\n"
            + frame
            + b"\r\n"
        )


@router.get(
    "/stream/{cameraId}",
)
async def streamCamera(
    cameraId: CameraId,
) -> StreamingResponse:
    cameraManager = cameraManagers[
        cameraId.value
    ]

    try:
        await cameraManager.start()
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    return StreamingResponse(
        generateMjpegFrames(
            cameraManager
        ),
        media_type=(
            "multipart/x-mixed-replace; "
            "boundary=frame"
        ),
    )
