from schemas.mode import (
    Mode,
    ModeResponse,
    ModeUpdate,
)


class ModeService:
    def __init__(self):
        self.currentMode = Mode.manage

    def getMode(
        self,
    ) -> ModeResponse:
        return ModeResponse(
            mode=self.currentMode
        )

    def updateMode(
        self,
        modeUpdate: ModeUpdate,
    ) -> ModeResponse:
        self.currentMode = (
            modeUpdate.mode
        )

        return ModeResponse(
            mode=self.currentMode
        )


modeService = ModeService()
