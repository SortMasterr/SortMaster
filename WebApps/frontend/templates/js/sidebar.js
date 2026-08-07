// js/sidebar.js

let isCollectMode = localStorage.getItem('isCollectMode') !== 'false';

// 1. 모드 상태 UI 반영
function updateSidebarUI() {
    const toggleBtn = document.getElementById('modeToggleBtn');
    const modeText = document.getElementById('modeText');
    const contentTitle = document.getElementById('contentTitle');
    const modeBadge = document.getElementById('modeBadge');
    const videoContainer = document.getElementById('videoContainer');

    if (!toggleBtn) return;

    if (isCollectMode) {
        toggleBtn.className = 'toggle-btn mode-collect';
        if (modeText) modeText.textContent = '관리모드';
        if (contentTitle) contentTitle.textContent = '현재 상태: 관리 모드';
        if (modeBadge) {
            modeBadge.textContent = '시스템 점검/관리 중';
            modeBadge.className = 'badge badge-collect';
        }
        if (videoContainer) videoContainer.classList.remove('warning-active');
    } else {
        toggleBtn.className = 'toggle-btn mode-admin';
        if (modeText) modeText.textContent = '수거모드';
        if (contentTitle) contentTitle.textContent = '현재 상태: 수거 모드';
        if (modeBadge) {
            modeBadge.textContent = '수거 가동 중';
            modeBadge.className = 'badge badge-admin';
        }
    }
}

// 2. 현재 URL 경로에 맞춰 active 클래스 적용
function updateActiveMenu() {
    // 현재 URL에서 파일명만 추출
    let currentFile = window.location.pathname.split('/').pop().split('?')[0].split('#')[0].toLowerCase();
    
    // 메인 페이지 예외 처리 (루트 접속 '/' 이거나 'index.html' 인 경우 'main.html'로 매칭)
    if (!currentFile || currentFile === '' || currentFile === 'index.html') {
        currentFile = 'main.html';
    }

    document.querySelectorAll('.nav-menu li').forEach(li => {
        const a = li.querySelector('a');
        if (!a) return;

        const rawHref = a.getAttribute('href') || '';
        const hrefFile = rawHref.split('/').pop().split('?')[0].split('#')[0].toLowerCase();

        // main.html과 index.html 교차 허용 매칭
        const isMainPage = (currentFile === 'main.html' || currentFile === 'index.html') && 
                           (hrefFile === 'main.html' || hrefFile === 'index.html');

        if (hrefFile === currentFile || isMainPage) {
            li.classList.add('active');
            a.classList.add('active');
        } else {
            li.classList.remove('active');
            a.classList.remove('active');
        }
    });
}

// 3. 사이드바 이벤트 및 초기화 실행
function initSidebarEvents() {
    updateActiveMenu();
    updateSidebarUI();

    const toggleBtn = document.getElementById('modeToggleBtn');
    if (toggleBtn) {
        toggleBtn.onclick = () => {
            isCollectMode = !isCollectMode;
            localStorage.setItem('isCollectMode', isCollectMode);
            updateSidebarUI();
        };
    }
}

// 4. 사이드바 HTML 동적 불러오기
function loadSidebar() {
    const container = document.getElementById('sidebar-container');
    if (!container) return;

    fetch('sidebar.html')
        .then(res => res.text())
        .then(html => {
            container.innerHTML = html;
            initSidebarEvents();
        })
        .catch(err => console.error('사이드바 로드 오류:', err));
}

document.addEventListener('DOMContentLoaded', loadSidebar);