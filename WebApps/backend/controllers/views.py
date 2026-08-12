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
            # MVP는 지점 2곳(각각 독립 젯슨 나노+카메라 1대). 4층(REST-4F-01)은
            # 고도화 단계에 추가 예정이라 아직 기본 목록에서 제외.
            "cameraIds": ["ELEV-01", "ELEV-02"],
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