let isCollectMode =
    localStorage.getItem("currentMode") !== "MANAGE";

function updateSidebarUI() {
    const toggleBtn = document.getElementById("modeToggleBtn");
    const modeText = document.getElementById("modeText");
    const contentTitle = document.getElementById("contentTitle");
    const modeBadge = document.getElementById("modeBadge");
    const videoContainer = document.getElementById("videoContainer");

    if (!toggleBtn) {
        return;
    }

    if (isCollectMode) {
        toggleBtn.className = "toggle-btn mode-collect";

        if (modeText) {
            modeText.textContent = "수거모드";
        }

        if (contentTitle) {
            contentTitle.textContent = "현재 상태: 수거 모드";
        }

        if (modeBadge) {
            modeBadge.textContent = "수거 가동 중";
            modeBadge.className = "badge badge-collect";
        }

        if (videoContainer) {
            videoContainer.classList.remove("warning-active");
        }
    } else {
        toggleBtn.className = "toggle-btn mode-admin";

        if (modeText) {
            modeText.textContent = "관리모드";
        }

        if (contentTitle) {
            contentTitle.textContent = "현재 상태: 관리 모드";
        }

        if (modeBadge) {
            modeBadge.textContent = "시스템 점검/관리 중";
            modeBadge.className = "badge badge-admin";
        }
    }
}

function updateActiveMenu() {
    const currentPath = window.location.pathname;

    document.querySelectorAll(".nav-menu li").forEach((menuItem) => {
        const link = menuItem.querySelector("a");

        if (!link) {
            return;
        }

        const linkPath = link.getAttribute("href");
        const isActive = linkPath === currentPath;

        menuItem.classList.toggle("active", isActive);
        link.classList.toggle("active", isActive);
    });
}

function initSidebarEvents() {
    updateActiveMenu();
    updateSidebarUI();

    const toggleBtn = document.getElementById("modeToggleBtn");

    if (!toggleBtn) {
        return;
    }

    toggleBtn.addEventListener("click", () => {
        isCollectMode = !isCollectMode;

        localStorage.setItem(
            "currentMode",
            isCollectMode ? "COLLECT" : "MANAGE"
        );

        updateSidebarUI();
    });
}

document.addEventListener("DOMContentLoaded", initSidebarEvents);