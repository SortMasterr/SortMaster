document.addEventListener("DOMContentLoaded", () => {
    /* 이전기록 샘플 데이터 설정 */
    const types = [
        {
            name: "병/캔/플라스틱",
            cls: "tag-plastic",
            bin: "캔/병/플라스틱 통",
        },
        {
            name: "일반쓰레기",
            cls: "general_waste",
            bin: "일반쓰레기통",
        },
        {
            name: "종이",
            cls: "tag-paper",
            bin: "종이 배출함",
        },
    ];

    const areas = ["4층", "12층"];
    const wrongBin = "일반쓰레기함";

    function pad(number) {
        return number.toString().padStart(2, "0");
    }

    /* 샘플 데이터 생성 */
    function generateData(count) {
        const rows = [];
        const now = new Date();

        for (let index = count; index >= 1; index--) {
            const type =
                types[Math.floor(Math.random() * types.length)];

            const area =
                areas[Math.floor(Math.random() * areas.length)];

            const randomMinutes =
                Math.floor(Math.random() * 180 + 5);

            const time = new Date(
                now.getTime()
                - (count - index) * 1000 * 60 * randomMinutes
            );

            const isMisclassified = Math.random() < 0.15;

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
                time: time,
                area: area,
                type: type.name,
                typeCls: type.cls,
                loc: location,
                result: result,
                alarm: alarm,
            });
        }

        return rows;
    }

    const data = generateData(56);

    const state = {
        sortKey: "idx",
        sortDir: "desc",
        page: 1,
        pageSize: 10,
    };

    function getElement(id) {
        return document.getElementById(id);
    }

    function formatTime(date) {
        const year = date.getFullYear();
        const month = pad(date.getMonth() + 1);
        const day = pad(date.getDate());
        const hour = pad(date.getHours());
        const minute = pad(date.getMinutes());
        const second = pad(date.getSeconds());

        return (
            `${year}-${month}-${day} `
            + `${hour}:${minute}:${second}`
        );
    }

    /* 필터와 정렬 적용 */
    function applyFilters() {
        const fromElement = getElement("fFrom");
        const toElement = getElement("fTo");
        const typeElement = getElement("fType");
        const resultElement = getElement("fResult");
        const alarmElement = getElement("fAlarm");

        const from =
            fromElement && fromElement.value
                ? new Date(`${fromElement.value}T00:00:00`)
                : null;

        const to =
            toElement && toElement.value
                ? new Date(`${toElement.value}T23:59:59`)
                : null;

        const selectedType =
            typeElement ? typeElement.value : "";

        const selectedResult =
            resultElement ? resultElement.value : "";

        const selectedAlarm =
            alarmElement ? alarmElement.value : "";

        const rows = data.filter((row) => {
            if (from && row.time < from) {
                return false;
            }

            if (to && row.time > to) {
                return false;
            }

            if (
                selectedType
                && row.type !== selectedType
            ) {
                return false;
            }

            if (
                selectedResult
                && row.result !== selectedResult
            ) {
                return false;
            }

            if (
                selectedAlarm === "on"
                && row.alarm !== true
            ) {
                return false;
            }

            if (
                selectedAlarm === "off"
                && row.alarm !== false
            ) {
                return false;
            }

            return true;
        });

        rows.sort((firstRow, secondRow) => {
            let firstValue = firstRow[state.sortKey];
            let secondValue = secondRow[state.sortKey];

            if (state.sortKey === "time") {
                firstValue = firstRow.time.getTime();
                secondValue = secondRow.time.getTime();
            }

            if (typeof firstValue === "string") {
                firstValue = firstValue.toLowerCase();
                secondValue = secondValue.toLowerCase();
            }

            if (firstValue < secondValue) {
                return state.sortDir === "asc" ? -1 : 1;
            }

            if (firstValue > secondValue) {
                return state.sortDir === "asc" ? 1 : -1;
            }

            return 0;
        });

        return rows;
    }

    /* 페이지네이션 출력 */
    function renderPagination(totalPages) {
        const pagination = getElement("pagination");

        if (!pagination) {
            return;
        }

        let html = `
            <button
                ${state.page === 1 ? "disabled" : ""}
                data-page="prev"
                type="button"
            >
                ‹
            </button>
        `;

        for (
            let pageNumber = 1;
            pageNumber <= totalPages;
            pageNumber++
        ) {
            html += `
                <button
                    data-page="${pageNumber}"
                    class="${
                        pageNumber === state.page
                            ? "active"
                            : ""
                    }"
                    type="button"
                >
                    ${pageNumber}
                </button>
            `;
        }

        html += `
            <button
                ${
                    state.page === totalPages
                        ? "disabled"
                        : ""
                }
                data-page="next"
                type="button"
            >
                ›
            </button>
        `;

        pagination.innerHTML = html;

        pagination
            .querySelectorAll("button")
            .forEach((button) => {
                button.addEventListener("click", () => {
                    const selectedPage =
                        button.dataset.page;

                    if (selectedPage === "prev") {
                        state.page = Math.max(
                            1,
                            state.page - 1
                        );
                    } else if (selectedPage === "next") {
                        state.page = Math.min(
                            totalPages,
                            state.page + 1
                        );
                    } else {
                        state.page =
                            Number.parseInt(
                                selectedPage,
                                10
                            );
                    }

                    render();
                });
            });
    }

    /* 상세 모달 열기 */
    function openModal(row) {
        const modalTitle = getElement("modalTitle");
        const modalTime = getElement("mTime");
        const modalArea = getElement("mArea");
        const modalType = getElement("mType");
        const modalLocation = getElement("mLoc");
        const modalResult = getElement("mResult");
        const modalAlarm = getElement("mAlarm");
        const modalBackdrop =
            getElement("modalBackdrop");

        if (modalTitle) {
            modalTitle.textContent =
                `RECORD #${String(row.idx).padStart(4, "0")}`;
        }

        if (modalTime) {
            modalTime.textContent =
                formatTime(row.time);
        }

        if (modalArea) {
            modalArea.textContent = row.area;
        }

        const typeObject =
            types.find((type) => type.name === row.type);

        const typeClass =
            typeObject ? typeObject.cls : "";

        if (modalType) {
            modalType.innerHTML = `
                <span class="tag ${typeClass}">
                    <span class="tag-dot"></span>
                    ${row.type}
                </span>
            `;
        }

        if (modalLocation) {
            modalLocation.textContent = row.loc;
        }

        if (modalResult) {
            const resultClass =
                row.result === "정상" ? "ok" : "err";

            modalResult.innerHTML = `
                <span class="status ${resultClass}">
                    ${row.result}
                </span>
            `;
        }

        const alarmClass =
            row.alarm ? "on" : "off";

        const alarmIcon = row.alarm
            ? '<i class="fa-solid fa-bell"></i>'
            : '<i class="fa-solid fa-bell-slash"></i>';

        const alarmText = row.alarm
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
            modalBackdrop.classList.add("show");
        }
    }

    /* 테이블 행 클릭 이벤트 연결 */
    function attachRowEvents() {
        document
            .querySelectorAll("#tbody tr[data-idx]")
            .forEach((tableRow) => {
                tableRow.addEventListener("click", () => {
                    const rowIndex =
                        Number.parseInt(
                            tableRow.dataset.idx,
                            10
                        );

                    const selectedRow =
                        data.find(
                            (row) => row.idx === rowIndex
                        );

                    if (selectedRow) {
                        openModal(selectedRow);
                    }
                });
            });
    }

    /* 화면 렌더링 */
    function render() {
        const filteredRows = applyFilters();

        const countAll = getElement("countAll");

        if (countAll) {
            countAll.textContent = data.length;
        }

        const today = new Date();

        function isToday(date) {
            return (
                date.getFullYear() === today.getFullYear()
                && date.getMonth() === today.getMonth()
                && date.getDate() === today.getDate()
            );
        }

        const normalCount =
            data.filter(
                (row) => row.result === "정상"
            ).length;

        const accuracy =
            data.length > 0
                ? (normalCount / data.length) * 100
                : 0;

        const statTotal = getElement("statTotal");
        const statToday = getElement("statToday");
        const statAccuracy =
            getElement("statAccuracy");
        const statAlarmOff =
            getElement("statAlarmOff");

        if (statTotal) {
            statTotal.innerHTML =
                `${data.length}<span>건</span>`;
        }

        if (statToday) {
            const todayCount =
                data.filter(
                    (row) => isToday(row.time)
                ).length;

            statToday.innerHTML =
                `${todayCount}<span>건</span>`;
        }

        if (statAccuracy) {
            statAccuracy.innerHTML =
                `${accuracy.toFixed(1)}<span>%</span>`;
        }

        if (statAlarmOff) {
            const alarmOffCount =
                data.filter(
                    (row) =>
                        row.result === "오분류"
                        && row.alarm === false
                ).length;

            statAlarmOff.innerHTML =
                `${alarmOffCount}<span>건</span>`;
        }

        const totalPages = Math.max(
            1,
            Math.ceil(
                filteredRows.length / state.pageSize
            )
        );

        if (state.page > totalPages) {
            state.page = totalPages;
        }

        const startIndex =
            (state.page - 1) * state.pageSize;

        const pageRows =
            filteredRows.slice(
                startIndex,
                startIndex + state.pageSize
            );

        const countShown =
            getElement("countShown");

        if (countShown) {
            countShown.textContent =
                filteredRows.length;
        }

        const tableBody = getElement("tbody");

        if (tableBody) {
            if (pageRows.length === 0) {
                tableBody.innerHTML = `
                    <tr class="empty-row">
                        <td colspan="6">
                            조건에 맞는 기록이 없습니다.
                        </td>
                    </tr>
                `;
            } else {
                tableBody.innerHTML =
                    pageRows
                        .map((row) => {
                            const typeObject =
                                types.find(
                                    (type) =>
                                        type.name === row.type
                                );

                            const typeClass =
                                typeObject
                                    ? typeObject.cls
                                    : "";

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

                                    <td>${row.area}</td>

                                    <td>
                                        <span class="tag ${typeClass}">
                                            <span class="tag-dot"></span>
                                            ${row.type}
                                        </span>
                                    </td>

                                    <td>${row.loc}</td>

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

    /* 테이블 정렬 */
    document
        .querySelectorAll("thead th[data-key]")
        .forEach((tableHeader) => {
            tableHeader.addEventListener(
                "click",
                () => {
                    const sortKey =
                        tableHeader.dataset.key;

                    if (state.sortKey === sortKey) {
                        state.sortDir =
                            state.sortDir === "asc"
                                ? "desc"
                                : "asc";
                    } else {
                        state.sortKey = sortKey;
                        state.sortDir = "asc";
                    }

                    render();
                }
            );
        });

    /* 필터 변경 */
    [
        "fFrom",
        "fTo",
        "fType",
        "fResult",
        "fAlarm",
    ].forEach((id) => {
        const field = getElement(id);

        if (field) {
            field.addEventListener(
                "change",
                () => {
                    state.page = 1;
                    render();
                }
            );
        }
    });

    /* 필터 초기화 */
    const resetButton = getElement("btnReset");

    if (resetButton) {
        resetButton.addEventListener("click", () => {
            [
                "fFrom",
                "fTo",
                "fType",
                "fResult",
                "fAlarm",
            ].forEach((id) => {
                const input = getElement(id);

                if (input) {
                    input.value = "";
                }
            });

            state.page = 1;
            render();
        });
    }

    /* 모달 닫기 버튼 */
    const modalClose = getElement("modalClose");

    if (modalClose) {
        modalClose.addEventListener("click", () => {
            const modalBackdrop =
                getElement("modalBackdrop");

            if (modalBackdrop) {
                modalBackdrop.classList.remove("show");
            }
        });
    }

    /* 모달 바깥 영역 클릭 */
    const modalBackdrop =
        getElement("modalBackdrop");

    if (modalBackdrop) {
        modalBackdrop.addEventListener(
            "click",
            (event) => {
                if (
                    event.target.id === "modalBackdrop"
                ) {
                    modalBackdrop.classList.remove(
                        "show"
                    );
                }
            }
        );
    }

    /* 최초 화면 출력 */
    render();
});