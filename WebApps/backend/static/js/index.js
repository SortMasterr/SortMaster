// js/main.js
// 사이드바 로딩/활성화 표시는 js/sidebar.js가 전담합니다.
// (main.html에서 sidebar.js를 main.js보다 먼저 불러오므로
//  전역 변수 isCollectMode는 sidebar.js에서 이미 선언되어 있습니다.)

// 메인 페이지 전용 JavaScript
// sidebar.js에서 선언한 isCollectMode를 사용합니다.

let alertTimer = null;

document.addEventListener("DOMContentLoaded", () => {
    initMainEvents();
});

function initMainEvents() {
    const testAlertBtn =
        document.getElementById("testAlertBtn");

    const fullscreenBtn =
        document.getElementById("fullscreenBtn");

    const videoContainer =
        document.getElementById("videoContainer");

    /* 오배출 경고 테스트 */
    if (testAlertBtn && videoContainer) {
        testAlertBtn.addEventListener("click", () => {
            /*
             * API 명세 기준:
             * 수거 모드에서는 알림을 발생시키지 않습니다.
             */
            if (isCollectMode) {
                alert(
                    "[안내] 현재 수거 모드이므로 " +
                    "오배출 알림이 작동하지 않습니다."
                );

                return;
            }

            if (alertTimer !== null) {
                clearTimeout(alertTimer);
            }

            videoContainer.classList.add(
                "warningActive"
            );

            alertTimer = setTimeout(() => {
                videoContainer.classList.remove(
                    "warningActive"
                );

                alertTimer = null;
            }, 5000);
        });
    }

    /* 전체화면 버튼 */
    if (fullscreenBtn && videoContainer) {
        fullscreenBtn.addEventListener("click", async () => {
            try {
                if (!document.fullscreenElement) {
                    await videoContainer.requestFullscreen();
                } else {
                    await document.exitFullscreen();
                }
            } catch (error) {
                console.error(
                    "전체화면 전환 오류:",
                    error
                );
            }
        });
    }
}