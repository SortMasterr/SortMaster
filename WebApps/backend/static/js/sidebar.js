let isCollectMode =
    localStorage.getItem(
        "currentMode"
    ) === "COLLECT";

let isModeSynchronized = false;

let sidebarSocket = null;
let reconnectTimer = null;
let sidebarWarningTimer = null;
let binFullAlertPollTimer = null;
let currentMisclassificationAlerts = [];

const physicalBinIds = new Set([
    "BIN-GENERAL",
    "BIN-PLASTIC-CAN",
    "BIN-COFFEE-CUP",
    "BIN-PAPER",
]);

const acknowledgedAlertsStorageKey =
    "sortMasterAcknowledgedMisclassificationIds";


function getLegacyAcknowledgedAlertIds() {
    try {
        const storedValue = JSON.parse(
            localStorage.getItem(
                acknowledgedAlertsStorageKey
            ) || "[]"
        );

        return new Set(
            Array.isArray(storedValue)
                ? storedValue
                : []
        );
    } catch (error) {
        console.warn(
            "미확인 알림 저장값을 읽지 못했습니다:",
            error
        );

        return new Set();
    }
}


function updateMisclassificationAlertBadge(count) {
    const badge = document.getElementById(
        "misclassificationAlertBadge"
    );

    if (!badge) {
        return;
    }

    badge.hidden = count === 0;
    badge.textContent = count > 99
        ? "99+"
        : String(count);
    badge.setAttribute(
        "aria-label",
        `미확인 오분류 ${count}건`
    );
}


function publishMisclassificationAlerts(alerts) {
    currentMisclassificationAlerts = alerts;
    window.sortMasterMisclassificationAlerts = alerts;

    updateMisclassificationAlertBadge(
        alerts.length
    );

    window.dispatchEvent(
        new CustomEvent(
            "sortMasterMisclassificationAlertsUpdated",
            {
                detail: {
                    alerts,
                },
            }
        )
    );
}


function getTodayStartIso() {
    const today = new Date();

    today.setHours(0, 0, 0, 0);

    return today.toISOString();
}


async function refreshMisclassificationAlerts() {
    try {
        const parameters = new URLSearchParams({
            from: getTodayStartIso(),
        });

        const response = await fetch(
            `/api/events?${parameters.toString()}`
        );

        if (!response.ok) {
            throw new Error(
                `오분류 알림 조회 실패: ${response.status}`
            );
        }

        const events = await response.json();
        const alerts = events
            .filter((eventData) => {
                return (
                    eventData.eventCategory ===
                        "misclassification" &&
                    eventData.isMisclassified === true &&
                    eventData.actionTaken !== "none" &&
                    eventData.acknowledgedAt == null
                );
            })
            .sort((left, right) => {
                return new Date(right.timestamp) -
                    new Date(left.timestamp);
            });

        publishMisclassificationAlerts(alerts);
    } catch (error) {
        console.warn(
            "미확인 오분류 알림을 갱신하지 못했습니다:",
            error
        );
    }
}


async function requestAlertAcknowledgement(
    path,
    body = null
) {
    const options = {
        method: "POST",
        headers: {},
    };

    if (body !== null) {
        options.headers["Content-Type"] =
            "application/json";
        options.body = JSON.stringify(body);
    }

    const response = await fetch(path, options);

    if (!response.ok) {
        throw new Error(
            `오분류 알림 확인 실패: ${response.status}`
        );
    }

    return response.json();
}


async function acknowledgeMisclassificationAlert(eventId) {
    try {
        await requestAlertAcknowledgement(
            `/api/events/${encodeURIComponent(eventId)}` +
                "/acknowledge"
        );
        await refreshMisclassificationAlerts();
    } catch (error) {
        console.warn(
            "오분류 알림을 확인하지 못했습니다:",
            error
        );
    }
}


async function acknowledgeAllMisclassificationAlerts() {
    const eventIds = currentMisclassificationAlerts.map(
        (alertData) => alertData.eventId
    );

    if (eventIds.length === 0) {
        return;
    }

    try {
        await requestAlertAcknowledgement(
            "/api/events/acknowledgeAll",
            { eventIds }
        );
        await refreshMisclassificationAlerts();
    } catch (error) {
        console.warn(
            "오분류 알림을 모두 확인하지 못했습니다:",
            error
        );
    }
}


async function migrateLegacyAcknowledgedAlerts() {
    const eventIds = Array.from(
        getLegacyAcknowledgedAlertIds()
    );

    if (eventIds.length === 0) {
        localStorage.removeItem(
            acknowledgedAlertsStorageKey
        );
        return;
    }

    try {
        await requestAlertAcknowledgement(
            "/api/events/acknowledgeAll",
            { eventIds }
        );
        localStorage.removeItem(
            acknowledgedAlertsStorageKey
        );
    } catch (error) {
        console.warn(
            "기존 오분류 확인 상태를 서버로 옮기지 못했습니다:",
            error
        );
    }
}


window.acknowledgeMisclassificationAlert =
    acknowledgeMisclassificationAlert;
window.acknowledgeAllMisclassificationAlerts =
    acknowledgeAllMisclassificationAlerts;


function setBinFullAlertVisible(isVisible) {
    const alertElement =
        document.getElementById(
            "binFullAlert"
        );

    if (!alertElement) {
        return;
    }

    alertElement.hidden = !isVisible;
    alertElement.setAttribute(
        "aria-hidden",
        String(!isVisible)
    );
}


async function refreshBinFullAlert() {
    const alertElement =
        document.getElementById(
            "binFullAlert"
        );

    if (!alertElement) {
        return;
    }

    if (!isModeSynchronized || isCollectMode) {
        setBinFullAlertVisible(false);
        return;
    }

    try {
        const response = await fetch(
            "/api/binStates"
        );

        if (!response.ok) {
            throw new Error(
                "쓰레기통 상태 조회 실패"
            );
        }

        const binStates = await response.json();
        const latestStateByBinId = new Map();

        if (Array.isArray(binStates)) {
            binStates.forEach((binState) => {
                if (!physicalBinIds.has(binState.binId)) {
                    return;
                }

                const previous = latestStateByBinId.get(
                    binState.binId
                );

                if (
                    !previous ||
                    new Date(binState.lastChangedAt) >
                        new Date(previous.lastChangedAt)
                ) {
                    latestStateByBinId.set(
                        binState.binId,
                        binState
                    );
                }
            });
        }

        const hasFullBin = Array.from(
            latestStateByBinId.values()
        ).some(
            (binState) =>
                binState.currentState === "FULL"
        );

        setBinFullAlertVisible(
            !isCollectMode && hasFullBin
        );
    } catch (error) {
        console.warn(
            "쓰레기통 가득참 상태를 갱신하지 못했습니다:",
            error
        );
    }
}


function applyMode(mode) {
    isCollectMode =
        mode === "COLLECT";
    isModeSynchronized = true;

    localStorage.setItem(
        "currentMode",
        mode
    );

    if (isCollectMode) {
        setBinFullAlertVisible(false);
    } else {
        refreshBinFullAlert();
    }

    updateSidebarUI();
}


function updateSidebarUI() {
    const modeToggleBtn =
        document.getElementById(
            "modeToggleBtn"
        );

    const modeText =
        document.getElementById(
            "modeText"
        );

    const contentTitle =
        document.getElementById(
            "contentTitle"
        );

    const modeBadge =
        document.getElementById(
            "modeBadge"
        );

    const videoContainer =
        document.getElementById(
            "videoContainer"
        );

    if (!modeToggleBtn) {
        return;
    }

    if (isCollectMode) {
        modeToggleBtn.className =
            "toggleBtn modeCollect";

        if (modeText) {
            modeText.textContent =
                "수거모드";
        }

        if (contentTitle) {
            contentTitle.textContent =
                "현재 상태: 수거 모드";
        }

        if (modeBadge) {
            modeBadge.textContent =
                "수거 가동 중";

            modeBadge.className =
                "badge badgeCollect";
        }

        if (videoContainer) {
            videoContainer.classList.remove(
                "warningActive"
            );
        }
    } else {
        modeToggleBtn.className =
            "toggleBtn modeAdmin";

        if (modeText) {
            modeText.textContent =
                "관리모드";
        }

        if (contentTitle) {
            contentTitle.textContent =
                "현재 상태: 관리 모드";
        }

        if (modeBadge) {
            modeBadge.textContent =
                "시스템 점검/관리 중";

            modeBadge.className =
                "badge badgeAdmin";
        }
    }
}


function updateActiveMenu() {
    const currentPath =
        window.location.pathname;

    document
        .querySelectorAll(
            ".navMenu li"
        )
        .forEach((menuItem) => {
            const link =
                menuItem.querySelector("a");

            if (!link) {
                return;
            }

            const linkPath =
                link.getAttribute("href");

            let isActive =
                linkPath === currentPath;

            if (
                linkPath === "/events" &&
                currentPath.startsWith(
                    "/events/"
                )
            ) {
                isActive = true;
            }

            menuItem.classList.toggle(
                "active",
                isActive
            );

            link.classList.toggle(
                "active",
                isActive
            );
        });
}


function showEventWarning() {
    if (isCollectMode) {
        return;
    }

    const videoContainer =
        document.getElementById(
            "videoContainer"
        );

    if (!videoContainer) {
        return;
    }

    if (sidebarWarningTimer !== null) {
        clearTimeout(
            sidebarWarningTimer
        );
    }

    videoContainer.classList.add(
        "warningActive"
    );

    sidebarWarningTimer =
        setTimeout(() => {
            videoContainer.classList.remove(
                "warningActive"
            );

            sidebarWarningTimer = null;
        }, 5000);
}


function connectSidebarSocket() {
    if (
        sidebarSocket !== null &&
        (
            sidebarSocket.readyState ===
                WebSocket.CONNECTING ||
            sidebarSocket.readyState ===
                WebSocket.OPEN
        )
    ) {
        return;
    }

    const protocol =
        window.location.protocol === "https:"
            ? "wss"
            : "ws";

    sidebarSocket = new WebSocket(
        `${protocol}://` +
        `${window.location.host}` +
        "/ws/events"
    );

    sidebarSocket.onopen = () => {
        refreshMisclassificationAlerts();
    };

    sidebarSocket.onmessage = (
        event
    ) => {
        const message =
            JSON.parse(event.data);

        window.dispatchEvent(
            new CustomEvent(
                "sortMasterWebSocketMessage",
                {
                    detail: message,
                }
            )
        );

        if (
            message.eventType ===
            "MODE_CHANGED"
        ) {
            applyMode(message.mode);
        }

        if (
            !isCollectMode &&
            message.eventType ===
            "MISCLASSIFICATION_DETECTED"
        ) {
            showEventWarning();
            refreshMisclassificationAlerts();
        }

        if (
            message.eventType ===
            "MISCLASSIFICATION_ACKNOWLEDGED"
        ) {
            refreshMisclassificationAlerts();
        }

        if (
            !isCollectMode &&
            message.eventType ===
            "BIN_OVERFLOW_DETECTED"
        ) {
            refreshBinFullAlert();
        }
    };

    sidebarSocket.onclose = () => {
        sidebarSocket = null;

        if (reconnectTimer !== null) {
            clearTimeout(
                reconnectTimer
            );
        }

        reconnectTimer = setTimeout(
            connectSidebarSocket,
            3000
        );
    };

    sidebarSocket.onerror = (
        error
    ) => {
        console.error(
            "WebSocket 연결 오류:",
            error
        );
    };
}


async function requestModeChange() {
    const modeToggleBtn =
        document.getElementById(
            "modeToggleBtn"
        );

    if (!modeToggleBtn) {
        return;
    }

    const nextMode =
        isCollectMode
            ? "MANAGE"
            : "COLLECT";

    modeToggleBtn.disabled = true;

    try {
        const response = await fetch(
            "/api/mode",
            {
                method: "POST",
                headers: {
                    "Content-Type":
                        "application/json"
                },
                body: JSON.stringify({
                    mode: nextMode
                })
            }
        );

        if (!response.ok) {
            throw new Error(
                `모드 변경 실패: ` +
                `${response.status}`
            );
        }

        const modeResponse =
            await response.json();

        applyMode(
            modeResponse.mode
        );
    } catch (error) {
        console.error(
            "모드 변경 오류:",
            error
        );

        alert(
            "모드를 변경하지 못했습니다."
        );
    } finally {
        modeToggleBtn.disabled = false;
    }
}


async function initSidebarEvents() {
    updateActiveMenu();
    updateSidebarUI();
    connectSidebarSocket();
    refreshBinFullAlert();
    await migrateLegacyAcknowledgedAlerts();
    await refreshMisclassificationAlerts();

    binFullAlertPollTimer =
        setInterval(
            refreshBinFullAlert,
            15000
        );

    const modeToggleBtn =
        document.getElementById(
            "modeToggleBtn"
        );

    if (!modeToggleBtn) {
        return;
    }

    modeToggleBtn.addEventListener(
        "click",
        requestModeChange
    );
}


window.addEventListener(
    "collectionTasksChanged",
    refreshBinFullAlert
);


document.addEventListener(
    "visibilitychange",
    () => {
        if (!document.hidden) {
            refreshMisclassificationAlerts();
        }
    }
);


document.addEventListener(
    "DOMContentLoaded",
    initSidebarEvents
);
