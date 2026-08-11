// js/dashboard.js
// 사이드바 로딩/활성화 표시는 js/sidebar.js가 전담합니다.
// (dashboard.html에서 sidebar.js를 dashboard.js보다 먼저 불러옵니다.)
// 대시보드 페이지 고유의 추가 동작이 생기면 이 파일에 작성하세요.
document.addEventListener(
    "DOMContentLoaded",
    async () => {
        const typeNameByClass = {
            general: "일반 쓰레기",
            paper: "종이",
            plastic: "플라스틱",
            coffeeCup: "커피 컵",
            mixed: "혼합 쓰레기",
            uncertain: "판별 불가",
        };

        const cameraNameById = {
            "ELEV-01": "엘리베이터 1호기",
            "ELEV-02": "엘리베이터 2호기",
            "REST-4F-01": "4층 휴게실",
        };

        function getElement(id) {
            return document.getElementById(id);
        }

        function pad(number) {
            return String(number).padStart(
                2,
                "0"
            );
        }

        function formatTime(timestamp) {
            const date = new Date(timestamp);

            if (Number.isNaN(date.getTime())) {
                return "-";
            }

            return (
                `${pad(date.getHours())}:` +
                `${pad(date.getMinutes())}:` +
                `${pad(date.getSeconds())}`
            );
        }

        function escapeHtml(value) {
            return String(value)
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll(
                    '"',
                    "&quot;"
                )
                .replaceAll(
                    "'",
                    "&#039;"
                );
        }

        async function requestJson(url) {
            const response =
                await fetch(url);

            if (!response.ok) {
                throw new Error(
                    `${url} 조회 실패: ` +
                    `HTTP ${response.status}`
                );
            }

            return response.json();
        }

        function convertStatistics(
            statistics
        ) {
            const countByClass = {};

            statistics.labels.forEach(
                (label, index) => {
                    countByClass[label] =
                        statistics.counts[
                            index
                        ] ?? 0;
                }
            );

            return countByClass;
        }

        function updateText(
            elementId,
            value
        ) {
            const element =
                getElement(elementId);

            if (element) {
                element.textContent =
                    value;
            }
        }

        function updateBar(
            elementId,
            count,
            maximumCount
        ) {
            const element =
                getElement(elementId);

            if (!element) {
                return;
            }

            const width =
                maximumCount > 0
                    ? (
                        count /
                        maximumCount
                    ) * 100
                    : 0;

            element.style.width =
                `${width}%`;
        }

        function renderSummary(
            events,
            countByClass
        ) {
            const totalDisposals =
                Object.values(
                    countByClass
                ).reduce(
                    (total, count) =>
                        total + count,
                    0
                );

            const totalMisclassified =
                events.filter(
                    (eventData) =>
                        eventData
                            .isMisclassified
                ).length;

            updateText(
                "totalDisposals",
                totalDisposals
            );

            updateText(
                "totalMisclassified",
                totalMisclassified
            );
        }

        function renderClassStatistics(
            countByClass
        ) {
            const generalCount =
                countByClass.general ?? 0;

            const plasticCount =
                countByClass.plastic ?? 0;

            const paperCount =
                countByClass.paper ?? 0;

            const coffeeCupCount =
                countByClass.coffeeCup ?? 0;

            const allCounts =
                Object.values(
                    countByClass
                );

            const maximumCount =
                Math.max(
                    ...allCounts,
                    1
                );

            updateText(
                "generalCount",
                generalCount
            );

            updateText(
                "plasticCount",
                plasticCount
            );

            updateText(
                "paperCount",
                paperCount
            );

            updateText(
                "coffeeCupCount",
                coffeeCupCount
            );

            updateBar(
                "generalBar",
                generalCount,
                maximumCount
            );

            updateBar(
                "plasticBar",
                plasticCount,
                maximumCount
            );

            updateBar(
                "paperBar",
                paperCount,
                maximumCount
            );

            updateBar(
                "coffeeCupBar",
                coffeeCupCount,
                maximumCount
            );
        }

        function createEventRow(
            eventData
        ) {
            const isMisclassified =
                eventData.isMisclassified;

            const warningActivated =
                eventData.actionTaken !==
                "none";

            const resultColor =
                isMisclassified
                    ? "#dc2626"
                    : "#16a34a";

            let resultText =
                isMisclassified
                    ? "오배출"
                    : "정상 분류";

            if (
                isMisclassified &&
                warningActivated
            ) {
                resultText += " 🚨";
            }

            const cameraName =
                cameraNameById[
                    eventData.cameraId
                ] ?? eventData.cameraId;

            const typeName =
                typeNameByClass[
                    eventData.detectedClass
                ] ??
                eventData.detectedClass;

            return `
                <tr
                    style="
                        border-bottom:
                        1px solid #f1f5f9;
                    "
                >
                    <td
                        style="
                            padding: 10px 4px;
                            color: #94a3b8;
                        "
                    >
                        ${formatTime(
                            eventData.timestamp
                        )}
                    </td>

                    <td
                        style="
                            padding: 10px 4px;
                        "
                    >
                        ${escapeHtml(
                            cameraName
                        )}
                    </td>

                    <td
                        style="
                            padding: 10px 4px;
                            color:
                            ${resultColor};
                            font-weight: 700;
                        "
                    >
                        ${escapeHtml(
                            typeName
                        )}
                    </td>

                    <td
                        style="
                            padding: 10px 4px;
                        "
                    >
                        ${escapeHtml(
                            eventData.cameraId
                        )}
                    </td>

                    <td
                        style="
                            padding: 10px 4px;
                            color:
                            ${resultColor};
                            font-weight: 700;
                            text-align: right;
                        "
                    >
                        ${resultText}
                    </td>
                </tr>
            `;
        }

        function renderRecentEvents(
            events
        ) {
            const tableBody =
                getElement(
                    "recentEventsBody"
                );

            if (!tableBody) {
                return;
            }

            if (events.length === 0) {
                tableBody.innerHTML = `
                    <tr>
                        <td
                            colspan="5"
                            style="
                                padding: 20px;
                                color: #94a3b8;
                                text-align: center;
                            "
                        >
                            저장된 이벤트가 없습니다.
                        </td>
                    </tr>
                `;

                return;
            }

            const recentEvents =
                events.slice(0, 5);

            tableBody.innerHTML =
                recentEvents
                    .map(createEventRow)
                    .join("");
        }

        function renderError(error) {
            console.error(
                "대시보드 조회 오류:",
                error
            );

            const tableBody =
                getElement(
                    "recentEventsBody"
                );

            if (tableBody) {
                tableBody.innerHTML = `
                    <tr>
                        <td
                            colspan="5"
                            style="
                                padding: 20px;
                                color: #dc2626;
                                text-align: center;
                            "
                        >
                            데이터를 불러오지
                            못했습니다.
                        </td>
                    </tr>
                `;
            }
        }

        async function loadDashboard() {
            try {
                const [
                    statistics,
                    events,
                ] = await Promise.all([
                    requestJson(
                        "/api/statistics"
                    ),
                    requestJson(
                        "/api/events"
                    ),
                ]);

                const countByClass =
                    convertStatistics(
                        statistics
                    );

                renderSummary(
                    events,
                    countByClass
                );

                renderClassStatistics(
                    countByClass
                );

                renderRecentEvents(
                    events
                );
            } catch (error) {
                renderError(error);
            }
        }

        await loadDashboard();
    }
);