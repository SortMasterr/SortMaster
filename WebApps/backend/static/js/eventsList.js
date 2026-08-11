document.addEventListener("DOMContentLoaded", () => {
    /* 분류 타입 */
    const types = [
        {
            name: "병/캔/플라스틱",
            className: "tagPlastic",
            bin: "캔/병/플라스틱 통",
        },
        {
            name: "일반쓰레기",
            className: "generalWaste",
            bin: "일반쓰레기통",
        },
        {
            name: "종이",
            className: "tagPaper",
            bin: "종이 배출함",
        },
    ];

    const areas = ["4층", "12층"];
    const wrongBin = "일반쓰레기함";

    const state = {
        sortKey: "idx",
        sortDirection: "desc",
        currentPage: 1,
        pageSize: 10,
    };

    function getElement(id) {
        return document.getElementById(id);
    }

    function pad(number) {
        return number
            .toString()
            .padStart(2, "0");
    }

    function formatTime(date) {
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

    /* Mock 데이터 생성 */
    function generateData(count) {
        const rows = [];
        const now = new Date();

        for (
            let index = count;
            index >= 1;
            index--
        ) {
            const type =
                types[
                    Math.floor(
                        Math.random() * types.length
                    )
                ];

            const area =
                areas[
                    Math.floor(
                        Math.random() * areas.length
                    )
                ];

            const randomMinutes =
                Math.floor(
                    Math.random() * 180 + 5
                );

            const time = new Date(
                now.getTime() -
                (count - index) *
                    1000 *
                    60 *
                    randomMinutes
            );

            const isMisclassified =
                Math.random() < 0.15;

            let location;
            let result;
            let alarm;

            if (isMisclassified) {
                location = wrongBin;
                result = "오분류";
                alarm = true;
            } else {
                location = type.bin;
                result = "정상";
                alarm = false;
            }

            rows.push({
                idx: index,
                time,
                area,
                type: type.name,
                typeClass: type.className,
                loc: location,
                result,
                alarm,
            });
        }

        return rows;
    }

    const data = generateData(56);

    /* 필터 및 정렬 */
    function applyFilters() {
        const fromElement =
            getElement("fFrom");

        const toElement =
            getElement("fTo");

        const typeElement =
            getElement("fType");

        const resultElement =
            getElement("fResult");

        const alarmElement =
            getElement("fAlarm");

        const fromDate =
            fromElement?.value
                ? new Date(
                    `${fromElement.value}T00:00:00`
                )
                : null;

        const toDate =
            toElement?.value
                ? new Date(
                    `${toElement.value}T23:59:59`
                )
                : null;

        const selectedType =
            typeElement?.value ?? "";

        const selectedResult =
            resultElement?.value ?? "";

        const selectedAlarm =
            alarmElement?.value ?? "";

        const filteredRows =
            data.filter((row) => {
                if (
                    fromDate &&
                    row.time < fromDate
                ) {
                    return false;
                }

                if (
                    toDate &&
                    row.time > toDate
                ) {
                    return false;
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

                if (
                    selectedAlarm === "on" &&
                    row.alarm !== true
                ) {
                    return false;
                }

                if (
                    selectedAlarm === "off" &&
                    row.alarm !== false
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
                        secondValue.toLowerCase();
                }

                if (firstValue < secondValue) {
                    return (
                        state.sortDirection === "asc"
                            ? -1
                            : 1
                    );
                }

                if (firstValue > secondValue) {
                    return (
                        state.sortDirection === "asc"
                            ? 1
                            : -1
                    );
                }

                return 0;
            }
        );

        return filteredRows;
    }

    /* 페이지네이션 */
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
                pageNumber === state.currentPage
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
                    state.currentPage === totalPages
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
                            selectedPage === "prev"
                        ) {
                            state.currentPage =
                                Math.max(
                                    1,
                                    state.currentPage - 1
                                );
                        } else if (
                            selectedPage === "next"
                        ) {
                            state.currentPage =
                                Math.min(
                                    totalPages,
                                    state.currentPage + 1
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

    /* 상세 모달 */
    function openModal(row) {
        const modalTitle =
            getElement("modalTitle");

        const modalTime =
            getElement("mTime");

        const modalArea =
            getElement("mArea");

        const modalType =
            getElement("mType");

        const modalLocation =
            getElement("mLoc");

        const modalResult =
            getElement("mResult");

        const modalAlarm =
            getElement("mAlarm");

        const modalBackdrop =
            getElement("modalBackdrop");

        if (modalTitle) {
            modalTitle.textContent =
                `RECORD #${String(row.idx).padStart(
                    4,
                    "0"
                )}`;
        }

        if (modalTime) {
            modalTime.textContent =
                formatTime(row.time);
        }

        if (modalArea) {
            modalArea.textContent = row.area;
        }

        if (modalType) {
            modalType.innerHTML = `
                <span class="tag ${row.typeClass}">
                    <span class="tagDot"></span>
                    ${row.type}
                </span>
            `;
        }

        if (modalLocation) {
            modalLocation.textContent =
                row.loc;
        }

        if (modalResult) {
            const resultClass =
                row.result === "정상"
                    ? "ok"
                    : "err";

            modalResult.innerHTML = `
                <span class="status ${resultClass}">
                    ${row.result}
                </span>
            `;
        }

        const alarmClass =
            row.alarm ? "on" : "off";

        const alarmIcon =
            row.alarm
                ? '<i class="fa-solid fa-bell"></i>'
                : '<i class="fa-solid fa-bell-slash"></i>';

        const alarmText =
            row.alarm
                ? "알림 울림 (부저 작동)"
                : "알림 미작동";

        if (modalAlarm) {
            modalAlarm.innerHTML = `
                <span class="alarm ${alarmClass}">
                    ${alarmIcon}
                    ${alarmText}
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

    /* 테이블 행 클릭 이벤트 */
    function attachRowEvents() {
        document
            .querySelectorAll(
                "#tbody tr[data-idx]"
            )
            .forEach((tableRow) => {
                tableRow.addEventListener(
                    "click",
                    () => {
                        const rowIndex =
                            Number.parseInt(
                                tableRow.dataset.idx,
                                10
                            );

                        const selectedRow =
                            data.find(
                                (row) =>
                                    row.idx === rowIndex
                            );

                        if (selectedRow) {
                            openModal(selectedRow);
                        }
                    }
                );
            });
    }

    /* 통계 카드 */
    function renderStatistics() {
        const today = new Date();

        const isToday = (date) => {
            return (
                date.getFullYear() ===
                    today.getFullYear() &&
                date.getMonth() ===
                    today.getMonth() &&
                date.getDate() ===
                    today.getDate()
            );
        };

        const normalCount =
            data.filter(
                (row) => row.result === "정상"
            ).length;

        const accuracy =
            data.length > 0
                ? (
                    normalCount /
                    data.length
                ) * 100
                : 0;

        const todayCount =
            data.filter(
                (row) => isToday(row.time)
            ).length;

        const alarmOffCount =
            data.filter(
                (row) =>
                    row.result === "오분류" &&
                    row.alarm === false
            ).length;

        const statTotal =
            getElement("statTotal");

        const statToday =
            getElement("statToday");

        const statAccuracy =
            getElement("statAccuracy");

        const statAlarmOff =
            getElement("statAlarmOff");

        if (statTotal) {
            statTotal.innerHTML =
                `${data.length}<span>건</span>`;
        }

        if (statToday) {
            statToday.innerHTML =
                `${todayCount}<span>건</span>`;
        }

        if (statAccuracy) {
            statAccuracy.innerHTML =
                `${accuracy.toFixed(1)}<span>%</span>`;
        }

        if (statAlarmOff) {
            statAlarmOff.innerHTML =
                `${alarmOffCount}<span>건</span>`;
        }
    }

    /* 테이블 출력 */
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
            state.currentPage > totalPages
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
                startIndex + state.pageSize
            );

        const tableBody =
            getElement("tbody");

        if (tableBody) {
            if (pageRows.length === 0) {
                tableBody.innerHTML = `
                    <tr class="emptyRow">
                        <td colspan="6">
                            조건에 맞는 기록이 없습니다.
                        </td>
                    </tr>
                `;
            } else {
                tableBody.innerHTML =
                    pageRows
                        .map((row) => {
                            const statusClass =
                                row.result === "정상"
                                    ? "ok"
                                    : "err";

                            const alarmClass =
                                row.alarm
                                    ? "on"
                                    : "off";

                            const alarmIcon =
                                row.alarm
                                    ? '<i class="fa-solid fa-bell"></i>'
                                    : '<i class="fa-solid fa-bell-slash"></i>';

                            const alarmText =
                                row.alarm
                                    ? "알림 울림"
                                    : "알림 미작동";

                            return `
                                <tr data-idx="${row.idx}">
                                    <td class="time">
                                        ${formatTime(row.time)}
                                    </td>

                                    <td>
                                        ${row.area}
                                    </td>

                                    <td>
                                        <span class="tag ${row.typeClass}">
                                            <span class="tagDot"></span>
                                            ${row.type}
                                        </span>
                                    </td>

                                    <td>
                                        ${row.loc}
                                    </td>

                                    <td>
                                        <span class="status ${statusClass}">
                                            <i class="fa-solid fa-circle"></i>
                                            ${row.result}
                                        </span>
                                    </td>

                                    <td>
                                        <span class="alarm ${alarmClass}">
                                            ${alarmIcon}
                                            ${alarmText}
                                        </span>
                                    </td>
                                </tr>
                            `;
                        })
                        .join("");
            }
        }

        renderPagination(totalPages);
        attachRowEvents();
    }

    /* 테이블 정렬 이벤트 */
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
                        state.sortKey === sortKey
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

    /* 필터 변경 이벤트 */
    [
        "fFrom",
        "fTo",
        "fType",
        "fResult",
        "fAlarm",
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

    /* 필터 초기화 */
    const resetButton =
        getElement("btnReset");

    if (resetButton) {
        resetButton.addEventListener(
            "click",
            () => {
                [
                    "fFrom",
                    "fTo",
                    "fType",
                    "fResult",
                    "fAlarm",
                ].forEach((id) => {
                    const input =
                        getElement(id);

                    if (input) {
                        input.value = "";
                    }
                });

                state.currentPage = 1;
                render();
            }
        );
    }

    /* 모달 닫기 버튼 */
    const modalClose =
        getElement("modalClose");

    if (modalClose) {
        modalClose.addEventListener(
            "click",
            closeModal
        );
    }

    /* 모달 바깥쪽 클릭 */
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

    /* ESC 키로 모달 닫기 */
    document.addEventListener(
        "keydown",
        (event) => {
            if (event.key === "Escape") {
                closeModal();
            }
        }
    );

    /* 최초 화면 출력 */
    render();
});