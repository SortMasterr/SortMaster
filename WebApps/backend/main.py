import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from controllers.api import (
    router as apiRouter,
)
from controllers.views import (
    router as viewsRouter,
)
from controllers.webSocket import (
    router as webSocketRouter,
)
from streaming.cameraManager import cameraManagers


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

    # RTSP 카메라는 백그라운드 ffmpeg 서브프로세스를 물고 있어서, 앱 종료 시
    # 정리 안 하면 --reload 재시작 등에서 고아 프로세스로 남을 수 있음.
    await asyncio.gather(
        *(
            cameraManager.stop()
            for cameraManager in cameraManagers.values()
        )
    )


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