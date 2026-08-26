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
