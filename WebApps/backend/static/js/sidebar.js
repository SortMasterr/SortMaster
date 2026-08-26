let isCollectMode =
    localStorage.getItem(
        "currentMode"
    ) === "COLLECT";

let sidebarSocket = null;
let reconnectTimer = null;
let sidebarWarningTimer = null;
let collectionAlertPollTimer = null;


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

    try {
        const [openResponse, acknowledgedResponse] =
            await Promise.all([
                fetch(
                    "/api/collectionTasks?" +
                    "taskStatus=OPEN&limit=1"
                ),
                fetch(
                    "/api/collectionTasks?" +
                    "taskStatus=ACKNOWLEDGED&limit=1"
                )
            ]);

        if (
            !openResponse.ok ||
            !acknowledgedResponse.ok
        ) {
            throw new Error(
                "수거 작업 상태 조회 실패"
            );
        }

        const [openTasks, acknowledgedTasks] =
            await Promise.all([
                openResponse.json(),
                acknowledgedResponse.json()
            ]);

        setBinFullAlertVisible(
            openTasks.total > 0 ||
            acknowledgedTasks.total > 0
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

    localStorage.setItem(
        "currentMode",
        mode
    );

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
            message.eventType ===
            "MISCLASSIFICATION_DETECTED"
        ) {
            showEventWarning();
        }

        if (
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


function initSidebarEvents() {
    updateActiveMenu();
    updateSidebarUI();
    connectSidebarSocket();
    refreshBinFullAlert();

    collectionAlertPollTimer =
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
    "DOMContentLoaded",
    initSidebarEvents
);
