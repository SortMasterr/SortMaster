from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates


router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def getIndexPage(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "currentMode": "MANAGE",
            "cameraId": "ELEV-01",
        },
    )


@router.get("/events")
async def getEventsPage(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="eventsList.html",
        context={},
    )


@router.get("/statistics")
async def getStatisticsPage(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="statistics.html",
        context={},
    )