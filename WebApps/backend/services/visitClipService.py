"""VISIT_CLIP 오케스트레이션 — presence 기반 방문 녹화와 GPU 트랙 신호(trackStarted/
aiDisposal/trackEnded)를 연결한다.

저장 여부(=presence 감지 기반 녹화)는 이 모듈과 완전히 무관하게 항상 실행된다(services/
presenceGateService.py 참고) — 여기서는 "이미 저장하기로 확정된 영상"을 확정/미확정으로
분류(라벨링)하는 것만 담당한다. 설계 배경은 .agentfiles/architecture.md의 "재학습용
미확정 방문 캡처", 결정 이유는 .agentfiles/decisionLog.md 참고.

트랙 시작(trackStarted)과 방문 녹화 종료(presence 이탈) 사이의 시간차를 메모리(activeTracks)로
연결한다. 보통 트랙은 사람이 아직 통 앞에 있는 동안 확정되므로(방문 녹화가 끝나기 전에
aiDisposal/trackEnded가 먼저 도착), clip은 클립을 만드는 시점에 이 메모리를 스캔해서
trackIds/matchedEventIds/unresolvedTrackIds를 채운다. clip이 이미 만들어진 "뒤"에
결과가 도착하는 드문 순서는 repositories/visitClipRepository.py의 DB 폴백(trackIds 배열
포함 쿼리)으로 처리한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from repositories.visitClipRepository import visitClipRepository
from schemas.event import CameraId
from schemas.visitClip import VisitClip

logger = logging.getLogger(__name__)

# 방문(presence) 구간 종료 시각 이후에도 트랙 신호가 살짝 늦게 도착할 수 있어(네트워크
# 지연 등) 클립 구간 매칭에 약간의 여유를 둔다 — 구간 자체가 아니라 매칭 관용치일 뿐이라
# .env로 노출하지 않음.
windowBufferSeconds = 5.0


def _normalizeToUtc(timestamp: datetime) -> datetime:
    """GPU(tracking2.py)가 타임존 정보 없는 timestamp를 보내면 UTC로 간주한다.

    createClipForVisit의 구간 비교(startedAt <= ... <= endedAt)는 presenceGateService가
    만드는 tz-aware(UTC) 값과 비교하는데, naive datetime과 비교하면 TypeError가 난다 —
    repositories/eventRepository.py의 normalizeDateTime과 동일한 이유·동일한 방어.
    """
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp


@dataclass
class _ActiveTrack:
    cameraId: CameraId
    startedAt: datetime
    matchedEventId: str | None = None
    # aiDisposal이 correct/incorrect로 확정한 경우 True(이벤트가 실제로 저장됐는지와는
    # 무관 — correct 판정은 애초에 EVENT를 저장하지 않으므로, 이 플래그가 없으면 정상
    # 분류된 방문도 재학습 후보로 잘못 잡힌다).
    resolved: bool = False


class VisitClipService:
    def __init__(self) -> None:
        self._activeTracks: dict[int, _ActiveTrack] = {}

    def recordTrackStarted(
        self,
        trackId: int,
        cameraId: CameraId,
        timestamp: datetime,
    ) -> None:
        if trackId in self._activeTracks:
            logger.warning(
                "[visitClipService] 이미 추적 중인 trackId=%s의 trackStarted 재수신",
                trackId,
            )
            return

        self._activeTracks[trackId] = _ActiveTrack(
            cameraId=cameraId,
            startedAt=_normalizeToUtc(timestamp),
        )

    async def registerAiDisposalResolution(
        self,
        trackId: int,
        eventId: str | None,
    ) -> None:
        """aiDisposal이 correct/incorrect로 확정될 때 호출한다.

        eventId는 실제로 EVENT가 저장된 경우(incorrect)에만 전달하고, correct처럼
        EVENT가 저장되지 않는 경우는 None으로 호출한다(그래도 방문 자체는 "해결됨"으로
        표시해야 재학습 후보에서 제외된다).

        eventId는 visitClip의 matchedEventIds 연결에만 사용한다. Event.imageFileId에는
        오분류 직전 5초 전용 GIF만 저장하므로 전체 방문 GIF를 반환하지 않는다.
        """
        active = self._activeTracks.get(trackId)

        if active is not None:
            active.resolved = True
            active.matchedEventId = eventId
            return

        if eventId is None:
            return

        matched = await visitClipRepository.addMatchedEvent(trackId, eventId)

        if not matched:
            logger.warning(
                "[visitClipService] aiDisposal에 대응하는 visitClip을 찾지 못함: "
                "trackId=%s",
                trackId,
            )
            return

    async def registerTrackEnded(self, trackId: int) -> None:
        if trackId in self._activeTracks:
            # resolved는 기본값 False라 별도 처리 없이도 clip 생성 시 미확정으로 잡힘 —
            # 그래도 신호 자체는 남겨서 재수신/디버깅에 참고할 수 있게 로그만 찍는다.
            logger.info(
                "[visitClipService] trackEnded(unresolved) 수신: trackId=%s", trackId
            )
            return

        matched = await visitClipRepository.addUnresolvedTrack(trackId)

        if not matched:
            logger.warning(
                "[visitClipService] trackEnded에 대응하는 visitClip을 찾지 못함: "
                "trackId=%s",
                trackId,
            )

    async def createClipForVisit(
        self,
        cameraId: CameraId,
        startedAt: datetime,
        endedAt: datetime,
        imageFileId: str,
    ) -> None:
        """presence 이탈로 녹화가 끝날 때마다 무조건 호출 — 판정 여부와 무관하게 저장한다.

        전체 방문 GIF는 VisitClip.imageFileId에만 저장한다. matchedEventIds는 관련
        이벤트를 찾기 위한 연결 정보이며 Event.imageFileId를 백필하지 않는다.
        """
        matchedTrackIds = [
            trackId
            for trackId, active in self._activeTracks.items()
            if active.cameraId == cameraId
            and startedAt <= active.startedAt <= endedAt + timedelta(seconds=windowBufferSeconds)
        ]
        matchedTracks = [
            (trackId, self._activeTracks.pop(trackId)) for trackId in matchedTrackIds
        ]

        matchedEventIds = [
            active.matchedEventId
            for _trackId, active in matchedTracks
            if active.matchedEventId is not None
        ]
        unresolvedTrackIds = [
            trackId for trackId, active in matchedTracks if not active.resolved
        ]

        clip = VisitClip(
            cameraId=cameraId,
            startedAt=startedAt,
            endedAt=endedAt,
            imageFileId=imageFileId,
            trackIds=[trackId for trackId, _active in matchedTracks],
            matchedEventIds=matchedEventIds,
            unresolvedTrackIds=unresolvedTrackIds,
        )
        await visitClipRepository.save(clip)


visitClipService = VisitClipService()
