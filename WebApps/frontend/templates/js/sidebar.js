// js/sidebar.js

const binFullStorageKey = 'isBinFull';

let isCollectMode = localStorage.getItem('isCollectMode') !== 'false';
let isBinFull = localStorage.getItem(binFullStorageKey) === 'true';

// 1. 모드 상태 UI 반영
function updateSidebarUI() {
    const toggleBtn = document.getElementById('modeToggleBtn');
    const modeText = document.getElementById('modeText');
    const contentTitle = document.getElementById('contentTitle');
    const modeBadge = document.getElementById('modeBadge');
    const videoContainer = document.getElementById('videoContainer');

    if (!toggleBtn) {
        return;
    }

    if (isCollectMode) {
        toggleBtn.className = 'toggle-btn mode-collect';

        if (modeText) {
            modeText.textContent = '관리모드';
        }

        if (contentTitle) {
            contentTitle.textContent = '현재 상태: 관리 모드';
        }

        if (modeBadge) {
            modeBadge.textContent = '시스템 점검/관리 중';
            modeBadge.className = 'badge badge-collect';
        }

        if (videoContainer) {
            videoContainer.classList.remove('warning-active');
        }
    } else {
        toggleBtn.className = 'toggle-btn mode-admin';

        if (modeText) {
            modeText.textContent = '수거모드';
        }

        if (contentTitle) {
            contentTitle.textContent = '현재 상태: 수거 모드';
        }

        if (modeBadge) {
            modeBadge.textContent = '수거 가동 중';
            modeBadge.className = 'badge badge-admin';
        }
    }
}

// 2. 쓰레기통 가득 참 알림 UI 반영
function updateBinFullAlert() {
    const binFullAlert = document.getElementById('binFullAlert');

    if (!binFullAlert) {
        return;
    }

    binFullAlert.hidden = !isBinFull;
    binFullAlert.setAttribute('aria-hidden', String(!isBinFull));
}

// 3. 쓰레기통 가득 참 상태 변경
function setBinFullState(nextState) {
    isBinFull = nextState === true;

    localStorage.setItem(binFullStorageKey, String(isBinFull));
    updateBinFullAlert();
}

// 다른 페이지 JS 또는 추후 WebSocket 코드에서 호출할 수 있도록 공개
window.setBinFullState = setBinFullState;

// 4. 현재 URL 경로에 맞춰 active 클래스 적용
function updateActiveMenu() {
    let currentFile = window.location.pathname
        .split('/')
        .pop()
        .split('?')[0]
        .split('#')[0]
        .toLowerCase();

    if (!currentFile || currentFile === 'index.html') {
        currentFile = 'main.html';
    }

    document.querySelectorAll('.nav-menu li').forEach((listItem) => {
        const link = listItem.querySelector('a');

        if (!link) {
            return;
        }

        const rawHref = link.getAttribute('href') || '';
        const hrefFile = rawHref
            .split('/')
            .pop()
            .split('?')[0]
            .split('#')[0]
            .toLowerCase();

        const isMainPage =
            (currentFile === 'main.html' || currentFile === 'index.html') &&
            (hrefFile === 'main.html' || hrefFile === 'index.html');

        if (hrefFile === currentFile || isMainPage) {
            listItem.classList.add('active');
            link.classList.add('active');
        } else {
            listItem.classList.remove('active');
            link.classList.remove('active');
        }
    });
}

// 5. 사이드바 이벤트 초기화
function initSidebarEvents() {
    updateActiveMenu();
    updateSidebarUI();
    updateBinFullAlert();

    const toggleBtn = document.getElementById('modeToggleBtn');

    if (toggleBtn) {
        toggleBtn.onclick = () => {
            isCollectMode = !isCollectMode;

            localStorage.setItem('isCollectMode', String(isCollectMode));
            updateSidebarUI();
        };
    }
}

// 6. 사이드바 HTML 동적 불러오기
function loadSidebar() {
    const container = document.getElementById('sidebar-container');

    if (!container) {
        return;
    }

    fetch('sidebar.html')
        .then((response) => {
            if (!response.ok) {
                throw new Error(`사이드바 응답 오류: ${response.status}`);
            }

            return response.text();
        })
        .then((html) => {
            container.innerHTML = html;
            initSidebarEvents();
        })
        .catch((error) => {
            console.error('사이드바 로드 오류:', error);
        });
}

// 다른 탭에서 가득 참 상태가 변경된 경우 동기화
window.addEventListener('storage', (event) => {
    if (event.key !== binFullStorageKey) {
        return;
    }

    isBinFull = event.newValue === 'true';
    updateBinFullAlert();
});

document.addEventListener('DOMContentLoaded', loadSidebar);