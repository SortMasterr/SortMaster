from schemas.mode import (
    Mode,
    ModeResponse,
    ModeUpdate,
)


class ModeService:
    def __init__(self):
        self.currentMode = Mode.manage
        self.changeRevision = 0
        self.lastChangeSource = "SYSTEM"

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
        return self._updateMode(
            modeUpdate,
            changeSource="MANUAL",
        )

    def updateModeAutomatically(
        self,
        modeUpdate: ModeUpdate,
    ) -> ModeResponse:
        return self._updateMode(
            modeUpdate,
            changeSource="AUTO_BIN_POSITION",
        )

    def getChangeMetadata(self) -> tuple[int, str]:
        return (
            self.changeRevision,
            self.lastChangeSource,
        )

    def _updateMode(
        self,
        modeUpdate: ModeUpdate,
        changeSource: str,
    ) -> ModeResponse:
        self.currentMode = (
            modeUpdate.mode
        )
        self.changeRevision += 1
        self.lastChangeSource = changeSource

        return ModeResponse(
            mode=self.currentMode
        )


modeService = ModeService()
