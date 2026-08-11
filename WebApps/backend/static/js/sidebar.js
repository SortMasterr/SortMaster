let isCollectMode =
    localStorage.getItem("currentMode") !== "MANAGE";

function updateSidebarUI() {
    const modeToggleBtn =
        document.getElementById("modeToggleBtn");

    const modeText =
        document.getElementById("modeText");

    const contentTitle =
        document.getElementById("contentTitle");

    const modeBadge =
        document.getElementById("modeBadge");

    const videoContainer =
        document.getElementById("videoContainer");

    if (!modeToggleBtn) {
        return;
    }

    if (isCollectMode) {
        modeToggleBtn.className =
            "toggleBtn modeCollect";

        if (modeText) {
            modeText.textContent = "수거모드";
        }

        if (contentTitle) {
            contentTitle.textContent =
                "현재 상태: 수거 모드";
        }

        if (modeBadge) {
            modeBadge.textContent = "수거 가동 중";
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
            modeText.textContent = "관리모드";
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
    const currentPath = window.location.pathname;

    document
        .querySelectorAll(".navMenu li")
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

            /*
             * 이벤트 상세 페이지도
             * 이전기록 메뉴로 표시합니다.
             */
            if (
                linkPath === "/events" &&
                currentPath.startsWith("/events/")
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

function initSidebarEvents() {
    updateActiveMenu();
    updateSidebarUI();

    const modeToggleBtn =
        document.getElementById("modeToggleBtn");

    if (!modeToggleBtn) {
        return;
    }

    modeToggleBtn.addEventListener("click", () => {
        isCollectMode = !isCollectMode;

        localStorage.setItem(
            "currentMode",
            isCollectMode
                ? "COLLECT"
                : "MANAGE"
        );

        updateSidebarUI();
    });
}

document.addEventListener(
    "DOMContentLoaded",
    initSidebarEvents
);