// js/main.js
// 사이드바 로딩/활성화 표시는 js/sidebar.js가 전담합니다.
// (main.html에서 sidebar.js를 main.js보다 먼저 불러오므로
//  전역 변수 isCollectMode는 sidebar.js에서 이미 선언되어 있습니다.)

let alertTimer = null;

document.addEventListener('DOMContentLoaded', () => {
    initMainEvents();
});

// 본문 페이지 전용 이벤트 (경고 테스트, 전체화면)
function initMainEvents() {
    const testAlertBtn = document.getElementById('testAlertBtn');
    const fullscreenBtn = document.getElementById('fullscreenBtn');
    const videoContainer = document.getElementById('videoContainer');

    if (testAlertBtn && videoContainer) {
        testAlertBtn.addEventListener('click', () => {
            if (isCollectMode) {
                alert('[안내] 현재 관리 모드 중이므로 알림이 Mute 처리됩니다.');
                return;
            }
            if (alertTimer) clearTimeout(alertTimer);
            videoContainer.classList.add('warning-active');
            alertTimer = setTimeout(() => {
                videoContainer.classList.remove('warning-active');
            }, 5000);
        });
    }

    if (fullscreenBtn && videoContainer) {
        fullscreenBtn.addEventListener('click', () => {
            if (!document.fullscreenElement) {
                videoContainer.requestFullscreen();
            } else {
                document.exitFullscreen();
            }
        });
    }
}
