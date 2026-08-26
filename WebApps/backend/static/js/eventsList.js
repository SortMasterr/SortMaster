document.addEventListener("DOMContentLoaded", async () => {
    const typeInfoByClass = {
        normal: {
            name: "일반쓰레기",
            className: "normalWaste",
        },
        paper: {
            name: "종이",
            className: "tagPaper",
        },
        recyclables: {
            name: "플라스틱·캔",
            className: "tagRecyclables",
        },
        coffeeCup: {
            name: "커피 컵",
            className: "tagPaper",
        },
    };

    const cameraInfoById = {
        "ELEV-TOP": "엘리베이터 위 카메라",
        "ELEV-SIDE": "엘리베이터 옆 카메라",
        "REST-4F-01": "4층 휴게실",
    };

    const state = {
        sortKey: "time",
        sortDirection: "desc",
        currentPage: 1,
        pageSize: 10,
    };

    let data = [];
    let loadErrorMessage = "";

    function getElement(id) {
        return document.getElementById(id);
    }

    function pad(number) {
        return String(number).padStart(2, "0");
    }

    function getTodayDateValue() {
        const today = new Date();

        return (
            `${today.getFullYear()}-` +
            `${pad(today.getMonth() + 1)}-` +
            `${pad(today.getDate())}`
        );
    }

    function setTodayDateFilters() {
        const todayValue =
            getTodayDateValue();

        const fromInput =
            getElement("fFrom");

        const toInput =
            getElement("fTo");

        if (fromInput) {
            fromInput.value = todayValue;
        }

        if (toInput) {
            toInput.value = todayValue;
        }
    }

    function formatTime(date) {
        if (
            !(date instanceof Date) ||
            Number.isNaN(date.getTime())
        ) {
            return "-";
        }

        const year = date.getFullYear();
        const month = pad(date.getMonth() + 1);
        const day = pad(date.getDate());
        const hour = pad(date.getHours());
        const minute = pad(date.getMinutes());
        const second = pad(date.getSeconds());

        return (
            `${year}-${month}-${day} ` +
            `${hour}:${minute}:${second}`
        );
    }

    function escapeHtml(value) {
        return String(value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function convertEventToRow(eventData) {
        const isOverflow =
            eventData.eventCategory === "overflow";

        const typeInfo = isOverflow
            ? {
                name: "쓰레기통 넘침",
                className: "tagOverflow",
            }
            : typeInfoByClass[eventData.detectedClass] ?? {
                name: eventData.detectedClass ?? "미분류",
                className: "normalWaste",
            };

        return {
            eventId: eventData.eventId,
            time: new Date(eventData.timestamp),

            area:
                cameraInfoById[eventData.cameraId] ??
                eventData.cameraId,

            type: typeInfo.name,
            typeClass: typeInfo.className,

            binId: eventData.binId ?? "-",

            result: isOverflow
                ? "넘침 감지"
                : eventData.isMisclassified
                    ? "오분류"
                    : "정상",

            eventCategory:
                eventData.eventCategory,
            notes:
                eventData.notes,
        };
    }

    function createEventsApiUrl() {
        const parameters =
            new URLSearchParams();

        const todayValue =
            getTodayDateValue();

        const fromValue =
            getElement("fFrom")?.value ||
            todayValue;

        const toValue =
            getElement("fTo")?.value ||
            todayValue;

        if (fromValue) {
            parameters.set(
                "from",
                new Date(
                    `${fromValue}T00:00:00`
                ).toISOString()
            );
        }

        if (toValue) {
            parameters.set(
                "to",
                new Date(
                    `${toValue}T23:59:59.999`
                ).toISOString()
            );
        }

        const queryString =
            parameters.toString();

        return queryString
            ? `/api/events?${queryString}`
            : "/api/events";
    }

    async function loadEvents() {
        const tableBody =
            getElement("tbody");

        if (tableBody) {
            tableBody.innerHTML = `
                <tr class="emptyRow">
                    <td colspan="4">
                        기록을 불러오는 중입니다.
                    </td>
                </tr>
            `;
        }

        loadErrorMessage = "";

        try {
            const response = await fetch(
                createEventsApiUrl()
            );

            if (!response.ok) {
                throw new Error(
                    `이벤트 조회 실패: HTTP ${response.status}`
                );
            }

            const events =
                await response.json();

            if (!Array.isArray(events)) {
                throw new Error(
                    "이벤트 응답 형식이 올바르지 않습니다."
                );
            }

            data = events.map(
                convertEventToRow
            );
        } catch (error) {
            console.error(
                "이벤트 목록 조회 오류:",
                error
            );

            data = [];

            loadErrorMessage =
                "기록을 불러오지 못했습니다. " +
                "서버 연결을 확인해주세요.";
        }
    }

    function applyFilters() {
        const fromValue =
            getElement("fFrom")?.value ?? "";

        const toValue =
            getElement("fTo")?.value ?? "";

        const selectedType =
            getElement("fType")?.value ?? "";

        const selectedResult =
            getElement("fResult")?.value ?? "";

        const filteredRows =
            data.filter((row) => {
                if (fromValue) {
                    const fromDate = new Date(
                        `${fromValue}T00:00:00`
                    );

                    if (row.time < fromDate) {
                        return false;
                    }
                }

                if (toValue) {
                    const toDate = new Date(
                        `${toValue}T23:59:59.999`
                    );

                    if (row.time > toDate) {
                        return false;
                    }
                }

                if (
                    selectedType &&
                    row.type !== selectedType
                ) {
                    return false;
                }

                if (
                    selectedResult &&
                    row.result !== selectedResult
                ) {
                    return false;
                }

                return true;
            });

        filteredRows.sort(
            (firstRow, secondRow) => {
                let firstValue =
                    firstRow[state.sortKey];

                let secondValue =
                    secondRow[state.sortKey];

                if (state.sortKey === "time") {
                    firstValue =
                        firstRow.time.getTime();

                    secondValue =
                        secondRow.time.getTime();
                }

                if (
                    typeof firstValue === "string"
                ) {
                    firstValue =
                        firstValue.toLowerCase();

                    secondValue =
                        String(secondValue)
                            .toLowerCase();
                }

                if (firstValue < secondValue) {
                    return (
                        state.sortDirection ===
                        "asc"
                            ? -1
                            : 1
                    );
                }

                if (firstValue > secondValue) {
                    return (
                        state.sortDirection ===
                        "asc"
                            ? 1
                            : -1
                    );
                }

                return 0;
            }
        );

        return filteredRows;
    }

    function renderPagination(totalPages) {
        const pagination =
            getElement("pagination");

        if (!pagination) {
            return;
        }

        let html = `
            <button
                data-page="prev"
                type="button"
                ${
                    state.currentPage === 1
                        ? "disabled"
                        : ""
                }
            >
                ‹
            </button>
        `;

        for (
            let pageNumber = 1;
            pageNumber <= totalPages;
            pageNumber++
        ) {
            const activeClass =
                pageNumber ===
                state.currentPage
                    ? "active"
                    : "";

            html += `
                <button
                    data-page="${pageNumber}"
                    class="${activeClass}"
                    type="button"
                >
                    ${pageNumber}
                </button>
            `;
        }

        html += `
            <button
                data-page="next"
                type="button"
                ${
                    state.currentPage ===
                    totalPages
                        ? "disabled"
                        : ""
                }
            >
                ›
            </button>
        `;

        pagination.innerHTML = html;

        pagination
            .querySelectorAll("button")
            .forEach((button) => {
                button.addEventListener(
                    "click",
                    () => {
                        const selectedPage =
                            button.dataset.page;

                        if (
                            selectedPage ===
                            "prev"
                        ) {
                            state.currentPage =
                                Math.max(
                                    1,
                                    state.currentPage -
                                        1
                                );
                        } else if (
                            selectedPage ===
                            "next"
                        ) {
                            state.currentPage =
                                Math.min(
                                    totalPages,
                                    state.currentPage +
                                        1
                                );
                        } else {
                            state.currentPage =
                                Number.parseInt(
                                    selectedPage,
                                    10
                                );
                        }

                        render();
                    }
                );
            });
    }

    function openModal(row) {
        const modalTitle =
            getElement("modalTitle");

        const modalTime =
            getElement("mTime");

        const modalArea =
            getElement("mArea");

        const modalType =
            getElement("mType");

        const modalBinId =
            getElement("mBinId");

        const modalResult =
            getElement("mResult");

        const modalBackdrop =
            getElement("modalBackdrop");

        if (modalTitle) {
            modalTitle.textContent =
                `EVENT ${row.eventId}`;
        }

        if (modalTime) {
            modalTime.textContent =
                formatTime(row.time);
        }

        if (modalArea) {
            modalArea.textContent =
                row.area;
        }

        if (modalType) {
            modalType.innerHTML = `
                <span
                    class="tag ${row.typeClass}"
                >
                    <span
                        class="tagDot"
                    ></span>
                    ${escapeHtml(row.type)}
                </span>
            `;
        }

        if (modalBinId) {
            modalBinId.textContent =
                row.binId;
        }

        if (modalResult) {
            const resultClass =
                row.result === "정상"
                    ? "ok"
                    : "err";

            modalResult.innerHTML = `
                <span
                    class="status ${resultClass}"
                >
                    ${row.result}
                </span>
            `;
        }

        if (modalBackdrop) {
            modalBackdrop.classList.add(
                "show"
            );
        }
    }

    function closeModal() {
        const modalBackdrop =
            getElement("modalBackdrop");

        if (modalBackdrop) {
            modalBackdrop.classList.remove(
                "show"
            );
        }
    }

    async function loadEventDetail(eventId) {
        const response = await fetch(
            "/api/events/" +
            encodeURIComponent(eventId)
        );

        if (!response.ok) {
            throw new Error(
                "Event detail request failed: HTTP " +
                response.status
            );
        }

        return convertEventToRow(
            await response.json()
        );
    }

    function attachRowEvents() {
        document
            .querySelectorAll(
                "#tbody tr[data-event-id]"
            )
            .forEach((tableRow) => {
                tableRow.addEventListener(
                    "click",
                    async () => {
                        const eventId =
                            tableRow.dataset
                                .eventId;

                        try {
                            const selectedRow =
                                await loadEventDetail(
                                    eventId
                                );

                            openModal(
                                selectedRow
                            );
                        } catch (error) {
                            console.error(
                                "Event detail load failed:",
                                error
                            );

                            alert(
                                "이벤트 상세 정보를 불러오지 못했습니다."
                            );
                        }
                    }
                );
            });
    }

    function renderStatistics() {
        const today = new Date();

        const todayCount =
            data.filter((row) => {
                return (
                    row.time.getFullYear() ===
                        today.getFullYear() &&
                    row.time.getMonth() ===
                        today.getMonth() &&
                    row.time.getDate() ===
                        today.getDate()
                );
            }).length;

        const misclassificationCount = data.filter(
            (row) => row.result === "오분류"
        ).length;

        const overflowCount = data.filter(
            (row) => row.result === "넘침 감지"
        ).length;

        const statTotal =
            getElement("statTotal");

        const statToday =
            getElement("statToday");

        const statMisclassification =
            getElement("statMisclassification");

        const statOverflow =
            getElement("statOverflow");

        if (statTotal) {
            statTotal.innerHTML =
                `${data.length}` +
                "<span>건</span>";
        }

        if (statToday) {
            statToday.innerHTML =
                `${todayCount}` +
                "<span>건</span>";
        }

        if (statMisclassification) {
            statMisclassification.innerHTML =
                `${misclassificationCount}` +
                "<span>건</span>";
        }

        if (statOverflow) {
            statOverflow.innerHTML =
                `${overflowCount}` +
                "<span>건</span>";
        }

    }

    function render() {
        const filteredRows =
            applyFilters();

        const countAll =
            getElement("countAll");

        const countShown =
            getElement("countShown");

        if (countAll) {
            countAll.textContent =
                data.length;
        }

        if (countShown) {
            countShown.textContent =
                filteredRows.length;
        }

        renderStatistics();

        const totalPages =
            Math.max(
                1,
                Math.ceil(
                    filteredRows.length /
                    state.pageSize
                )
            );

        if (
            state.currentPage >
            totalPages
        ) {
            state.currentPage =
                totalPages;
        }

        const startIndex =
            (
                state.currentPage - 1
            ) * state.pageSize;

        const pageRows =
            filteredRows.slice(
                startIndex,
                startIndex +
                    state.pageSize
            );

        const tableBody =
            getElement("tbody");

        if (!tableBody) {
            return;
        }

        if (pageRows.length === 0) {
            tableBody.innerHTML = `
                <tr class="emptyRow">
                    <td colspan="5">
                        ${
                            loadErrorMessage ||
                            "조건에 맞는 기록이 없습니다."
                        }
                    </td>
                </tr>
            `;
        } else {
            tableBody.innerHTML =
                pageRows
                    .map((row) => {
                        const statusClass =
                            row.result ===
                            "정상"
                                ? "ok"
                                : "err";

                        return `
                            <tr
                                data-event-id="${escapeHtml(
                                    row.eventId
                                )}"
                            >
                                <td class="time">
                                    ${formatTime(
                                        row.time
                                    )}
                                </td>

                                <td>
                                    ${escapeHtml(
                                        row.area
                                    )}
                                </td>

                                <td>
                                    <span
                                        class="tag ${row.typeClass}"
                                    >
                                        <span
                                            class="tagDot"
                                        ></span>

                                        ${escapeHtml(
                                            row.type
                                        )}
                                    </span>
                                </td>

                                <td>
                                    ${escapeHtml(
                                        row.binId
                                    )}
                                </td>

                                <td>
                                    <span
                                        class="status ${statusClass}"
                                    >
                                        <i
                                            class="fa-solid fa-circle"
                                        ></i>

                                        ${row.result}
                                    </span>
                                </td>

                            </tr>
                        `;
                    })
                    .join("");
        }

        renderPagination(totalPages);
        attachRowEvents();
    }

    async function reloadEvents() {
        state.currentPage = 1;

        await loadEvents();

        render();
    }

    document
        .querySelectorAll(
            "thead th[data-key]"
        )
        .forEach((tableHeader) => {
            tableHeader.addEventListener(
                "click",
                () => {
                    const sortKey =
                        tableHeader.dataset.key;

                    if (
                        state.sortKey ===
                        sortKey
                    ) {
                        state.sortDirection =
                            state.sortDirection ===
                            "asc"
                                ? "desc"
                                : "asc";
                    } else {
                        state.sortKey =
                            sortKey;

                        state.sortDirection =
                            "asc";
                    }

                    render();
                }
            );
        });

    [
        "fFrom",
        "fTo",
    ].forEach((id) => {
        const field =
            getElement(id);

        if (field) {
            field.addEventListener(
                "change",
                async () => {
                    if (!field.value) {
                        field.value =
                            getTodayDateValue();
                    }

                    await reloadEvents();
                }
            );
        }
    });

    [
        "fType",
        "fResult",
    ].forEach((id) => {
        const field =
            getElement(id);

        if (field) {
            field.addEventListener(
                "change",
                () => {
                    state.currentPage = 1;
                    render();
                }
            );
        }
    });

    const resetButton =
        getElement("btnReset");

    if (resetButton) {
        resetButton.addEventListener(
            "click",
            async () => {
                [
                    "fType",
                    "fResult",
                ].forEach((id) => {
                    const input =
                        getElement(id);

                    if (input) {
                        input.value = "";
                    }
                });

                setTodayDateFilters();

                await reloadEvents();
            }
        );
    }

    const modalClose =
        getElement("modalClose");

    if (modalClose) {
        modalClose.addEventListener(
            "click",
            closeModal
        );
    }

    const modalBackdrop =
        getElement("modalBackdrop");

    if (modalBackdrop) {
        modalBackdrop.addEventListener(
            "click",
            (event) => {
                if (
                    event.target ===
                    modalBackdrop
                ) {
                    closeModal();
                }
            }
        );
    }

    document.addEventListener(
        "keydown",
        (event) => {
            if (event.key === "Escape") {
                closeModal();
            }
        }
    );

    setTodayDateFilters();

    await loadEvents();

    render();
});
