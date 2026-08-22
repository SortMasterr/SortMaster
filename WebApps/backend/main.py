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
from repositories.binStateRepository import binStateRepository
from repositories.eventRepository import eventRepository
from repositories.mongoClient import (
    closeMongoClient,
    pingMongo,
)
from services.overflowDetectionService import (
    overflowDetectionService,
)
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
        await overflowDetectionService.start()
        yield
    finally:
        try:
            await overflowDetectionService.stop()
        finally:
            try:
                await recordingService.shutdown()
            finally:
                try:
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
