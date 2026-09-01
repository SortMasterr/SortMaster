// static/js/index.js
//
// 사이드바 로딩, 메뉴 활성화 및 모드 전환은
// sidebar.js가 담당합니다.

document.addEventListener(
    "DOMContentLoaded",
    initMainEvents
);


function initMainEvents() {
    initContainerFullscreen();
    initVideoPaneFullscreen();
    initMisclassificationAlerts();
}


const alertTypeNameByClass = {
    normal: "일반쓰레기",
    paper: "종이",
    recyclables: "플라스틱·캔",
    coffeeCup: "커피 컵",
};

const alertBinNameByType = {
    normal: "일반쓰레기통",
    paper: "종이 수거함",
    recyclables: "재활용 수거함",
    coffeeCup: "커피 컵 수거함",
};

const alertCameraNameById = {
    "ELEV-TOP": "엘리베이터 위 카메라",
    "ELEV-SIDE": "엘리베이터 옆 카메라",
    "REST-4F-01": "4층 휴게실",
};


function formatAlertTime(timestamp) {
    const date = new Date(timestamp);

    if (Number.isNaN(date.getTime())) {
        return "시간 미상";
    }

    return date.toLocaleTimeString(
        "ko-KR",
        {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
        }
    );
}


function buildAlertDetail(alertData) {
    const detectedName =
        alertTypeNameByClass[
            alertData.detectedClass
        ] ?? alertData.detectedClass ?? "미분류";
    const binName =
        alertBinNameByType[
            alertData.binType
        ] ?? alertData.binType ?? "수거함 미상";
    const details = [
        `감지: ${detectedName}`,
        `투입 위치: ${binName}`,
    ];

    return details.join(" · ");
}


function createAlertIcon(className) {
    const icon = document.createElement("i");

    icon.className = className;
    icon.setAttribute("aria-hidden", "true");

    return icon;
}


function createMisclassificationAlertItem(
    alertData
) {
    const item = document.createElement("article");
    const top = document.createElement("div");
    const title = document.createElement("span");
    const time = document.createElement("time");
    const camera = document.createElement("p");
    const detail = document.createElement("p");
    const actions = document.createElement("div");
    const recordLink = document.createElement("a");
    const acknowledgeButton =
        document.createElement("button");

    item.className = "eventAlertItem";
    item.setAttribute("role", "listitem");

    top.className = "eventAlertItemTop";
    title.className = "eventAlertItemTitle";
    title.textContent = "오분류 감지";

    time.className = "eventAlertTime";
    time.dateTime = alertData.timestamp;
    time.textContent = formatAlertTime(
        alertData.timestamp
    );

    top.append(title, time);

    camera.className = "eventAlertCamera";
    camera.textContent =
        alertCameraNameById[
            alertData.cameraId
        ] ?? alertData.cameraId;

    detail.className = "eventAlertDetail";
    detail.textContent = buildAlertDetail(
        alertData
    );

    actions.className = "eventAlertActions";

    recordLink.className = "alertRecordLink";
    recordLink.href =
        `/events?eventId=${encodeURIComponent(
            alertData.eventId
        )}`;
    recordLink.append(
        createAlertIcon(
            "fa-solid fa-arrow-up-right-from-square"
        ),
        document.createTextNode("기록 보기")
    );

    acknowledgeButton.className =
        "alertAcknowledgeBtn";
    acknowledgeButton.type = "button";
    acknowledgeButton.append(
        createAlertIcon("fa-solid fa-check"),
        document.createTextNode("확인")
    );
    acknowledgeButton.addEventListener(
        "click",
        () => {
            window
                .acknowledgeMisclassificationAlert?.(
                    alertData.eventId
                );
        }
    );

    actions.append(
        recordLink,
        acknowledgeButton
    );
    item.append(
        top,
        camera,
        detail,
        actions
    );

    return item;
}


function renderMisclassificationAlerts(alerts) {
    const alertList = document.getElementById(
        "eventAlertList"
    );
    const emptyState = document.getElementById(
        "eventAlertEmpty"
    );
    const countBadge = document.getElementById(
        "eventAlertCount"
    );
    const acknowledgeAllButton =
        document.getElementById(
            "acknowledgeAllAlertsBtn"
        );

    if (
        !alertList ||
        !emptyState ||
        !countBadge ||
        !acknowledgeAllButton
    ) {
        return;
    }

    const safeAlerts = Array.isArray(alerts)
        ? alerts
        : [];
    const count = safeAlerts.length;

    alertList.replaceChildren(
        ...safeAlerts.map(
            createMisclassificationAlertItem
        )
    );

    countBadge.textContent = count > 99
        ? "99+"
        : String(count);
    countBadge.classList.toggle(
        "isEmpty",
        count === 0
    );
    emptyState.hidden = count > 0;
    alertList.hidden = count === 0;
    acknowledgeAllButton.hidden = count === 0;
}


function initMisclassificationAlerts() {
    renderMisclassificationAlerts(
        window.sortMasterMisclassificationAlerts ??
            []
    );

    window.addEventListener(
        "sortMasterMisclassificationAlertsUpdated",
        (event) => {
            renderMisclassificationAlerts(
                event.detail?.alerts
            );
        }
    );

    document
        .getElementById(
            "acknowledgeAllAlertsBtn"
        )
        ?.addEventListener(
            "click",
            () => {
                window
                    .acknowledgeAllMisclassificationAlerts?.();
            }
        );
}


/* 두 카메라를 함께 전체화면으로 표시 */
function initContainerFullscreen() {
    const fullscreenBtn =
        document.getElementById("fullscreenBtn");

    const videoContainer =
        document.getElementById("videoContainer");

    if (!fullscreenBtn || !videoContainer) {
        return;
    }

    fullscreenBtn.addEventListener(
        "click",
        async () => {
            try {
                /*
                 * 개별 카메라가 전체화면인 경우에도
                 * 버튼을 누르면 전체화면을 종료합니다.
                 */
                if (document.fullscreenElement) {
                    await document.exitFullscreen();
                    return;
                }

                clearFocusedPane(videoContainer);

                await videoContainer.requestFullscreen();
            } catch (error) {
                console.error(
                    "두 카메라 전체화면 전환 오류:",
                    error
                );
            }
        }
    );

    document.addEventListener(
        "fullscreenchange",
        () => {
            const isContainerFullscreen =
                document.fullscreenElement ===
                videoContainer;

            updateFullscreenButton(
                fullscreenBtn,
                isContainerFullscreen
            );

            /*
             * 전체화면을 완전히 종료하면
             * 개별 카메라 선택 상태도 초기화합니다.
             */
            if (!document.fullscreenElement) {
                clearFocusedPane(videoContainer);
            }
        }
    );

    updateFullscreenButton(
        fullscreenBtn,
        false
    );
}


/* 전체화면 버튼 아이콘 및 안내 문구 변경 */
function updateFullscreenButton(
    fullscreenBtn,
    isFullscreen
) {
    const icon =
        fullscreenBtn.querySelector("i");

    if (icon) {
        icon.className = isFullscreen
            ? "fa-solid fa-compress"
            : "fa-solid fa-expand";
    }

    const buttonLabel = isFullscreen
        ? "전체화면 종료"
        : "두 카메라 전체화면 보기";

    fullscreenBtn.title = buttonLabel;

    fullscreenBtn.setAttribute(
        "aria-label",
        buttonLabel
    );
}


/* 각 카메라의 개별 확대 기능 */
function initVideoPaneFullscreen() {
    const videoContainer =
        document.getElementById("videoContainer");

    const videoPanes =
        document.querySelectorAll(".videoPane");

    if (!videoContainer || videoPanes.length === 0) {
        return;
    }

    videoPanes.forEach((videoPane) => {
        videoPane.addEventListener(
            "click",
            async () => {
                await toggleVideoPaneFullscreen(
                    videoContainer,
                    videoPane
                );
            }
        );

        videoPane.addEventListener(
            "keydown",
            async (event) => {
                if (
                    event.key !== "Enter"
                    && event.key !== " "
                ) {
                    return;
                }

                event.preventDefault();

                await toggleVideoPaneFullscreen(
                    videoContainer,
                    videoPane
                );
            }
        );
    });
}


/*
 * 일반 화면:
 * 선택한 videoPane 자체를 브라우저 전체화면으로 전환합니다.
 *
 * 두 화면 전체화면:
 * videoContainer 전체화면은 유지하면서 선택한 Pane만 표시합니다.
 * 이렇게 해야 브라우저의 전체화면 전환 제한과 충돌하지 않습니다.
 */
async function toggleVideoPaneFullscreen(
    videoContainer,
    videoPane
) {
    try {
        const fullscreenElement =
            document.fullscreenElement;

        /*
         * 선택한 카메라 자체가 전체화면인 경우
         * 다시 클릭하면 전체화면을 종료합니다.
         */
        if (fullscreenElement === videoPane) {
            await document.exitFullscreen();
            return;
        }

        /*
         * 두 화면이 함께 전체화면인 상태
         */
        if (fullscreenElement === videoContainer) {
            const isAlreadyFocused =
                videoPane.classList.contains(
                    "paneFocused"
                );

            if (isAlreadyFocused) {
                clearFocusedPane(videoContainer);
                return;
            }

            focusVideoPane(
                videoContainer,
                videoPane
            );

            return;
        }

        /*
         * 일반 화면에서는 선택한 카메라만
         * 브라우저 전체화면으로 전환합니다.
         */
        clearFocusedPane(videoContainer);

        await videoPane.requestFullscreen();
    } catch (error) {
        console.error(
            "개별 카메라 전체화면 전환 오류:",
            error
        );
    }
}


/* 두 화면 전체화면에서 카메라 하나만 표시 */
function focusVideoPane(
    videoContainer,
    selectedPane
) {
    const videoPanes =
        videoContainer.querySelectorAll(
            ".videoPane"
        );

    videoContainer.classList.add(
        "singlePaneMode"
    );

    videoPanes.forEach((videoPane) => {
        videoPane.classList.toggle(
            "paneFocused",
            videoPane === selectedPane
        );
    });
}


/* 개별 카메라 선택 상태 해제 */
function clearFocusedPane(videoContainer) {
    videoContainer.classList.remove(
        "singlePaneMode"
    );

    videoContainer
        .querySelectorAll(".videoPane")
        .forEach((videoPane) => {
            videoPane.classList.remove(
                "paneFocused"
            );
        });
}
