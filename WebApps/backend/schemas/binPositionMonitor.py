from pydantic import BaseModel

from schemas.mode import Mode


class BinPositionMonitorStatus(BaseModel):
    enabled: bool
    state: str
    configuredMarkerIds: list[int]
    visibleMarkerIds: list[int]
    baselineConfigured: bool
    automaticallyChangedMode: bool
    currentMode: Mode
    lastFrameAt: str | None = None
    message: str

