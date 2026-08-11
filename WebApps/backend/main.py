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


app = FastAPI(
    title="스마트 수거 관리 시스템",
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