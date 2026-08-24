import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# 기본 로깅 레벨(WARNING)에서는 services/presenceGateService.py 등의 logger.info가
# 콘솔에 안 보임 — 상태 전이 로그를 보려면 INFO 이상은 나와야 함
logging.basicConfig(level=logging.INFO)

from controllers.api import (
    router as apiRouter,
)
from controllers.views import (
    router as viewsRouter,
)
from controllers.webSocket import (
    router as webSocketRouter,
)
from repositories.binStateRepository import binStateRepository
from repositories.eventRepository import eventRepository
from repositories.mongoClient import (
    closeMongoClient,
    pingMongo,
)
from services.presenceGateService import presenceGateService
from services.recordingService import recordingService
from streaming.cameraManager import cameraManagers


mongoStartupTimeoutSeconds = 5.0


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await asyncio.wait_for(
            pingMongo(),
            timeout=mongoStartupTimeoutSeconds,
        )
        await eventRepository.ensureIndexes()
        await binStateRepository.ensureIndexes()
        await presenceGateService.start()
        yield
    finally:
        try:
            await presenceGateService.shutdown()
        finally:
            try:
                await recordingService.shutdown()
            finally:
                try:
                    # RTSP 카메라는 백그라운드 ffmpeg 서브프로세스를 물고 있어서, 여기서
                    # 정리 안 하면 --reload 재시작 등에서 고아 프로세스로 남을 수 있음.
                    await asyncio.gather(
                        *(
                            cameraManager.stop()
                            for cameraManager
                            in cameraManagers.values()
                        ),
                        return_exceptions=True,
                    )
                finally:
                    closeMongoClient()


app = FastAPI(
    title="스마트 수거 관리 시스템",
    lifespan=lifespan,
)


app.mount(
    "/static",
    StaticFiles(
        directory="static"
    ),
    name="static",
)


app.include_router(viewsRouter)
app.include_router(apiRouter)
app.include_router(webSocketRouter)
