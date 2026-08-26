// js/dashboard.js
// 사이드바 로딩/활성화 표시는 js/sidebar.js가 전담합니다.
// (dashboard.html에서 sidebar.js를 dashboard.js보다 먼저 불러옵니다.)
// 대시보드 페이지 고유의 추가 동작이 생기면 이 파일에 작성하세요.
document.addEventListener(
    "DOMContentLoaded",
    async () => {
        const typeNameByClass = {
            normal: "일반 쓰레기",
            paper: "종이",
            recyclables: "플라스틱·캔",
            coffeeCup: "커피 컵",
        };

        const cameraNameById = {
            "ELEV-TOP": "엘리베이터 위 카메라",
            "ELEV-SIDE": "엘리베이터 옆 카메라",
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

        function renderSummary(statistics) {
            updateText(
                "totalDisposals",
                statistics.totalEventCount ?? 0
            );

            updateText(
                "totalMisclassified",
                statistics.misclassificationCount ?? 0
            );

            updateText(
                "totalOverflow",
                statistics.overflowCount ?? 0
            );
        }

        function renderClassStatistics(
            countByClass
        ) {
            const normalCount =
                countByClass.normal ?? 0;

            const recyclablesCount =
                countByClass.recyclables ?? 0;

            const paperCount =
                countByClass.paper ?? 0;

            const coffeeCupCount =
                countByClass.coffeeCup ?? 0;

            const displayedCounts = [
                normalCount,
                recyclablesCount,
                paperCount,
                coffeeCupCount,
            ];

            const maximumCount =
                Math.max(
                    ...displayedCounts,
                    1
                );

            updateText(
                "normalCount",
                normalCount
            );

            updateText(
                "recyclablesCount",
                recyclablesCount
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
                "normalBar",
                normalCount,
                maximumCount
            );

            updateBar(
                "recyclablesBar",
                recyclablesCount,
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
            const isOverflow =
                eventData.eventCategory === "overflow";

            const isMisclassified =
                eventData.isMisclassified;

            const warningActivated =
                eventData.actionTaken !==
                "none";

            const resultColor = isOverflow
                ? "#d97706"
                : isMisclassified
                    ? "#dc2626"
                    : "#16a34a";

            let resultText = isOverflow
                ? "넘침 감지"
                : isMisclassified
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

            const typeName = isOverflow
                ? "쓰레기통 넘침"
                : typeNameByClass[
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

        function formatDateTime(timestamp) {
            const date = new Date(timestamp);
            return Number.isNaN(date.getTime())
                ? "-"
                : date.toLocaleString("ko-KR", { hour12: false });
        }

        function setupReportEmailSettingsForm() {
            const modal = getElement(
                "reportEmailSettingsModal"
            );
            const openButton = getElement(
                "openReportEmailSettingsButton"
            );
            const form = getElement(
                "reportEmailSettingsForm"
            );
            const recipientInput = getElement(
                "reportRecipient"
            );
            const status = getElement(
                "reportEmailSettingsStatus"
            );
            const confirmButton = getElement(
                "confirmReportEmailButton"
            );

            if (
                !modal ||
                !openButton ||
                !form ||
                !recipientInput ||
                !status ||
                !confirmButton
            ) {
                return;
            }

            function setStatus(message, isSuccess = false) {
                status.textContent = message;
                status.classList.toggle(
                    "isSuccess",
                    isSuccess
                );
            }

            async function openModal() {
                modal.hidden = false;
                setStatus("저장된 이메일 설정을 불러오는 중입니다.");
                try {
                    const response = await fetch(
                        "/api/reports/email"
                    );
                    const result = await response.json();
                    if (!response.ok) {
                        throw new Error(
                            result.detail ||
                            "이메일 설정을 불러오지 못했습니다."
                        );
                    }
                    recipientInput.value =
                        result.recipient || "";
                    setStatus(
                        result.configured
                            ? "현재 자동 보고서 수신 이메일입니다."
                            : "현재 자동 보고서 이메일을 수신하지 않습니다.",
                        result.configured
                    );
                } catch (error) {
                    setStatus(
                        error.message ||
                        "이메일 설정을 불러오지 못했습니다."
                    );
                }
                recipientInput.focus();
            }

            function closeModal() {
                if (confirmButton.disabled) {
                    return;
                }
                modal.hidden = true;
            }

            async function saveSettings(event) {
                event.preventDefault();
                if (!form.reportValidity()) {
                    return;
                }

                const body = {
                    recipient: recipientInput.value.trim() || null,
                };

                confirmButton.disabled = true;
                confirmButton.textContent = "저장 중...";
                setStatus(
                    body.recipient
                        ? "자동 보고서 수신 이메일을 저장하는 중입니다."
                        : "자동 보고서 이메일 수신을 해제하는 중입니다."
                );

                try {
                    const response = await fetch(
                        "/api/reports/email",
                        {
                            method: "POST",
                            headers: {
                                "Content-Type": "application/json",
                            },
                            body: JSON.stringify(body),
                        }
                    );
                    const result = await response.json();

                    if (!response.ok) {
                        const detail = Array.isArray(result.detail)
                            ? result.detail
                                .map((item) => item.msg)
                                .join(" ")
                            : result.detail;
                        throw new Error(
                            detail || "이메일 설정 저장에 실패했습니다."
                        );
                    }

                    setStatus(
                        result.configured
                            ? `${result.recipient} 주소로 설정했습니다. 다음 예약 시각부터 자동 발송됩니다.`
                            : "자동 보고서 이메일 수신을 해제했습니다.",
                        true
                    );
                } catch (error) {
                    setStatus(
                        error.message || "이메일 설정 저장에 실패했습니다."
                    );
                } finally {
                    confirmButton.disabled = false;
                    confirmButton.textContent = "확인";
                }
            }

            openButton.addEventListener(
                "click",
                openModal
            );
            form.addEventListener(
                "submit",
                saveSettings
            );
            modal.querySelectorAll(
                "[data-report-modal-close]"
            ).forEach((element) => {
                element.addEventListener(
                    "click",
                    closeModal
                );
            });
            document.addEventListener(
                "keydown",
                (event) => {
                    if (
                        event.key === "Escape" &&
                        !modal.hidden
                    ) {
                        closeModal();
                    }
                }
            );
        }

        function formatDuration(seconds) {
            if (seconds === null || seconds === undefined) {
                return "-";
            }
            const minutes = Math.round(seconds / 60);
            return minutes < 60
                ? `${minutes}분`
                : `${Math.floor(minutes / 60)}시간 ${minutes % 60}분`;
        }

        function renderCollectionAutomation(status, taskList) {
            updateText("collectionOpenCount", status.openTaskCount ?? 0);
            updateText("collectionAcknowledgedCount", status.acknowledgedTaskCount ?? 0);
            updateText("collectionEscalatedCount", status.escalatedTaskCount ?? 0);
            updateText("collectionCompletedCount", status.completedTodayCount ?? 0);
            updateText("collectionAverageTime", formatDuration(status.averageProcessingSeconds));
            updateText("collectionHeartbeat", formatDateTime(status.lastHeartbeatAt));

            const workerStatus = getElement("collectionWorkerStatus");
            if (workerStatus) {
                const label = !status.enabled
                    ? "비활성화"
                    : status.workerStatus === "RUNNING"
                        ? "정상 가동"
                        : status.workerStatus === "NOT_STARTED"
                            ? "워커 미실행"
                            : status.workerStatus;
                workerStatus.textContent = label;
                workerStatus.classList.toggle("isRunning", status.enabled && status.workerStatus === "RUNNING");
                workerStatus.classList.toggle("isFailed", status.enabled && status.workerStatus !== "RUNNING");
            }

            const tasksBody = getElement("collectionTasksBody");
            if (tasksBody) {
                tasksBody.innerHTML = taskList.tasks.length
                    ? taskList.tasks.map((task) => {
                        const closed = ["COMPLETED", "CANCELLED"].includes(task.taskStatus);
                        const acknowledge = task.taskStatus === "OPEN"
                            ? `<button class="collectionActionButton" data-collection-action="acknowledge" data-task-id="${escapeHtml(task.collectionTaskId)}">확인</button>`
                            : "";
                        const complete = !closed
                            ? `<button class="collectionActionButton complete" data-collection-action="complete" data-task-id="${escapeHtml(task.collectionTaskId)}">완료</button>`
                            : "-";
                        return `<tr>
                            <td>${escapeHtml(formatDateTime(task.detectedAt))}</td>
                            <td>${escapeHtml(task.taskStatus)}</td>
                            <td>${task.escalationLevel}단계</td>
                            <td>${acknowledge}${complete}</td>
                        </tr>`;
                    }).join("")
                    : '<tr><td colspan="4">수거 작업이 없습니다.</td></tr>';
            }

            const runsBody = getElement("collectionRunsBody");
            if (runsBody) {
                runsBody.innerHTML = status.recentRuns.length
                    ? status.recentRuns.map((run) => `<tr>
                        <td>${escapeHtml(formatDateTime(run.attemptedAt))}</td>
                        <td>${escapeHtml(run.actionType)}</td>
                        <td>${escapeHtml(run.recipientRole)}</td>
                        <td>${escapeHtml(run.status)}${run.errorType ? ` (${escapeHtml(run.errorType)})` : ""}</td>
                    </tr>`).join("")
                    : '<tr><td colspan="4">RPA 실행 이력이 없습니다.</td></tr>';
            }
        }

        async function loadCollectionAutomation() {
            const [status, taskList] = await Promise.all([
                requestJson("/api/collectionAutomation/status"),
                requestJson("/api/collectionTasks?limit=20"),
            ]);
            renderCollectionAutomation(status, taskList);
        }

        function setupCollectionTaskActions() {
            const tasksBody = getElement("collectionTasksBody");
            if (!tasksBody) {
                return;
            }
            tasksBody.addEventListener("click", async (event) => {
                const button = event.target.closest("[data-collection-action]");
                if (!button) {
                    return;
                }
                button.disabled = true;
                try {
                    const response = await fetch(
                        `/api/collectionTasks/${encodeURIComponent(button.dataset.taskId)}/${button.dataset.collectionAction}`,
                        { method: "POST" }
                    );
                    const result = await response.json();
                    if (!response.ok) {
                        throw new Error(result.detail || "수거 작업 처리에 실패했습니다.");
                    }
                    await loadCollectionAutomation();
                    window.dispatchEvent(
                        new Event(
                            "collectionTasksChanged"
                        )
                    );
                } catch (error) {
                    window.alert(error.message || "수거 작업 처리에 실패했습니다.");
                } finally {
                    button.disabled = false;
                }
            });
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

                renderSummary(statistics);

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

        setupReportEmailSettingsForm();
        setupCollectionTaskActions();
        await Promise.all([
            loadDashboard(),
            loadCollectionAutomation().catch((error) => {
                const status = getElement("collectionWorkerStatus");
                if (status) {
                    status.textContent = "조회 실패";
                    status.classList.add("isFailed");
                    status.title = error.message;
                }
            }),
        ]);
    }
);
