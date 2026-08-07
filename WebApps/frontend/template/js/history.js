document.addEventListener('DOMContentLoaded', () => {
    /* ---------------- 1. 사이드바 HTML 동적 포함 ---------------- */
    fetch('sidebar.html')
        .then(response => response.text())
        .then(data => {
            const sidebarContainer = document.getElementById('sidebar-container');
            if (sidebarContainer) {
                sidebarContainer.innerHTML = data;
                // 사이드바 DOM 삽입 완료 후 sidebar.js의 이벤트 연결 함수 호출
                if (typeof initSidebarEvents === 'function') {
                    initSidebarEvents();
                }
            }
        })
        .catch(error => console.error('사이드바 로드 오류:', error));

    /* ---------------- 2. 이전기록 데이터 & 테이블 로직 ---------------- */
    const TYPES = [
        { name: '일반쓰레기', cls: 'general_waste', bin: '일반쓰레기통' },
        { name: '종이', cls: 'tag-paper', bin: '종이 배출함' },
        { name: '캔', cls: 'tag-can', bin: '캔/병/플라스틱 통' },
        { name: '병', cls: 'tag-glass', bin: '캔/병/플라스틱 통' },
        { name: '플라스틱', cls: 'tag-plastic', bin: '캔/병/플라스틱 통' },
    ];
    const AREAS = ['4층', '12층'];
    const WRONG_BIN = '일반쓰레기함';

    function pad(n) { return n.toString().padStart(2, '0'); }

    // 샘플 데이터 생성 (area 속성 추가)
    function genData(n) {
        const rows = [];
        let now = new Date();
        for (let i = n; i >= 1; i--) {
            const t = TYPES[Math.floor(Math.random() * TYPES.length)];
            const area = AREAS[Math.floor(Math.random() * AREAS.length)];
            const time = new Date(now.getTime() - (n - i) * 1000 * 60 * Math.floor(Math.random() * 180 + 5));
            const isMisclassified = Math.random() < 0.15;

            let loc, result, alarm;
            if (isMisclassified) {
                loc = WRONG_BIN;
                result = '오분류';
                alarm = Math.random() > 0.08;
            } else {
                loc = t.bin;
                result = '정상';
                alarm = false;
            }

            rows.push({ idx: i, time, area, type: t.name, typeCls: t.cls, loc, result, alarm });
        }
        return rows;
    }

    const DATA = genData(56);
    let state = { sortKey: 'idx', sortDir: 'desc', page: 1, pageSize: 10 };

    const el = id => document.getElementById(id);

    function fmtTime(d) {
        const y = d.getFullYear(), m = pad(d.getMonth() + 1), day = pad(d.getDate());
        const h = pad(d.getHours()), mi = pad(d.getMinutes()), s = pad(d.getSeconds());
        return `${y}-${m}-${day} ${h}:${mi}:${s}`;
    }

    function applyFilters() {
        const fFrom = el('fFrom');
        const fTo = el('fTo');
        const fType = el('fType');
        const fResult = el('fResult');
        const fAlarm = el('fAlarm');

        const from = fFrom && fFrom.value ? new Date(fFrom.value + 'T00:00:00') : null;
        const to = fTo && fTo.value ? new Date(fTo.value + 'T23:59:59') : null;
        const type = fType ? fType.value : '';
        const resultF = fResult ? fResult.value : '';
        const alarmF = fAlarm ? fAlarm.value : '';

        let rows = DATA.filter(r => {
            if (from && r.time < from) return false;
            if (to && r.time > to) return false;
            if (type && r.type !== type) return false;
            if (resultF && r.result !== resultF) return false;
            if (alarmF === 'on' && r.alarm !== true) return false;
            if (alarmF === 'off' && r.alarm !== false) return false;
            return true;
        });

        rows.sort((a, b) => {
            let av = a[state.sortKey], bv = b[state.sortKey];
            if (state.sortKey === 'time') { av = a.time.getTime(); bv = b.time.getTime(); }
            if (typeof av === 'string') { av = av.toLowerCase(); bv = bv.toLowerCase(); }
            if (av < bv) return state.sortDir === 'asc' ? -1 : 1;
            if (av > bv) return state.sortDir === 'asc' ? 1 : -1;
            return 0;
        });

        return rows;
    }

    function render() {
        const filtered = applyFilters();
        if (el('countAll')) el('countAll').textContent = DATA.length;

        const today = new Date();
        const isToday = d => d.getFullYear() === today.getFullYear() && d.getMonth() === today.getMonth() && d.getDate() === today.getDate();
        const normalCount = DATA.filter(r => r.result === '정상').length;
        const accuracy = DATA.length ? (normalCount / DATA.length * 100) : 0;

        if (el('statTotal')) el('statTotal').innerHTML = DATA.length + '<span>건</span>';
        if (el('statToday')) el('statToday').innerHTML = DATA.filter(r => isToday(r.time)).length + '<span>건</span>';
        if (el('statAccuracy')) el('statAccuracy').innerHTML = accuracy.toFixed(1) + '<span>%</span>';
        if (el('statAlarmOff')) el('statAlarmOff').innerHTML = DATA.filter(r => r.result === '오분류' && r.alarm === false).length + '<span>건</span>';

        const totalPages = Math.max(1, Math.ceil(filtered.length / state.pageSize));
        if (state.page > totalPages) state.page = totalPages;
        const startIdx = (state.page - 1) * state.pageSize;
        const pageRows = filtered.slice(startIdx, startIdx + state.pageSize);

        if (el('countShown')) el('countShown').textContent = filtered.length;

        const tbody = el('tbody');
        if (tbody) {
            if (pageRows.length === 0) {
                tbody.innerHTML = `<tr class="empty-row"><td colspan="6">조건에 맞는 기록이 없습니다.</td></tr>`;
            } else {
                // 헤더 6개 열과 일치하도록 6개의 <td> 생성
                tbody.innerHTML = pageRows.map(r => {
                    const typeObj = TYPES.find(t => t.name === r.type);
                    const typeCls = typeObj ? typeObj.cls : '';
                    const statusCls = r.result === '정상' ? 'ok' : 'err';
                    const alarmCls = r.alarm ? 'on' : 'off';
                    const alarmIcon = r.alarm ? '<i class="fa-solid fa-bell"></i>' : '<i class="fa-solid fa-bell-slash"></i>';
                    const alarmText = r.alarm ? '알림 울림' : '알림 미작동';
                    return `
                    <tr data-idx="${r.idx}">
                        <td class="time">${fmtTime(r.time)}</td>
                        <td>${r.area}</td>
                        <td><span class="tag ${typeCls}"><span class="tag-dot"></span>${r.type}</span></td>
                        <td>${r.loc}</td>
                        <td><span class="status ${statusCls}"><i class="fa-solid fa-circle"></i> ${r.result}</span></td>
                        <td><span class="alarm ${alarmCls}">${alarmIcon} ${alarmText}</span></td>
                    </tr>`;
                }).join('');
            }
        }

        renderPagination(totalPages);
        attachRowEvents();
    }

    function renderPagination(totalPages) {
        const wrap = el('pagination');
        if (!wrap) return;

        let html = `<button ${state.page === 1 ? 'disabled' : ''} data-p="prev">‹</button>`;
        const p = state.page;
        for (let i = 1; i <= totalPages; i++) {
            html += `<button data-p="${i}" class="${i === p ? 'active' : ''}">${i}</button>`;
        }
        html += `<button ${state.page === totalPages ? 'disabled' : ''} data-p="next">›</button>`;
        wrap.innerHTML = html;

        wrap.querySelectorAll('button').forEach(b => {
            b.addEventListener('click', () => {
                const val = b.dataset.p;
                if (val === 'prev') state.page = Math.max(1, state.page - 1);
                else if (val === 'next') state.page = Math.min(totalPages, state.page + 1);
                else state.page = parseInt(val);
                render();
            });
        });
    }

    function attachRowEvents() {
        document.querySelectorAll('#tbody tr[data-idx]').forEach(tr => {
            tr.addEventListener('click', () => {
                const idx = parseInt(tr.dataset.idx);
                const r = DATA.find(d => d.idx === idx);
                if (r) openModal(r);
            });
        });
    }

    /* 테이블 정렬 이벤트 */
    document.querySelectorAll('thead th[data-key]').forEach(th => {
        th.addEventListener('click', () => {
            const key = th.dataset.key;
            if (state.sortKey === key) { state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc'; }
            else { state.sortKey = key; state.sortDir = 'asc'; }
            render();
        });
    });

    /* 필터 변경 이벤트 */
    ['fFrom', 'fTo', 'fType', 'fResult', 'fAlarm'].forEach(id => {
        const field = el(id);
        if (field) {
            field.addEventListener('change', () => { state.page = 1; render(); });
        }
    });

    const btnReset = el('btnReset');
    if (btnReset) {
        btnReset.addEventListener('click', () => {
            ['fFrom', 'fTo', 'fType', 'fResult', 'fAlarm'].forEach(id => {
                const input = el(id);
                if (input) input.value = '';
            });
            state.page = 1;
            render();
        });
    }

    /* 상세 모달 제어 */
    function openModal(r) {
        if (el('modalTitle')) el('modalTitle').textContent = `RECORD #${String(r.idx).padStart(4, '0')}`;
        if (el('mTime')) el('mTime').textContent = fmtTime(r.time);
        if (el('mArea')) el('mArea').textContent = r.area;

        const typeObj = TYPES.find(t => t.name === r.type);
        const typeCls = typeObj ? typeObj.cls : '';
        if (el('mType')) el('mType').innerHTML = `<span class="tag ${typeCls}"><span class="tag-dot"></span>${r.type}</span>`;
        if (el('mLoc')) el('mLoc').textContent = r.loc;
        if (el('mResult')) el('mResult').innerHTML = `<span class="status ${r.result === '정상' ? 'ok' : 'err'}">${r.result}</span>`;

        const mAlarmCls = r.alarm ? 'on' : 'off';
        const mAlarmIcon = r.alarm ? '<i class="fa-solid fa-bell"></i>' : '<i class="fa-solid fa-bell-slash"></i>';
        const mAlarmText = r.alarm ? '알림 울림 (부저 작동)' : '알림 미작동';
        if (el('mAlarm')) el('mAlarm').innerHTML = `<span class="alarm ${mAlarmCls}">${mAlarmIcon} ${mAlarmText}</span>`;

        const modalBackdrop = el('modalBackdrop');
        if (modalBackdrop) modalBackdrop.classList.add('show');
    }

    const modalClose = el('modalClose');
    if (modalClose) {
        modalClose.addEventListener('click', () => {
            const modalBackdrop = el('modalBackdrop');
            if (modalBackdrop) modalBackdrop.classList.remove('show');
        });
    }

    const modalBackdrop = el('modalBackdrop');
    if (modalBackdrop) {
        modalBackdrop.addEventListener('click', (e) => {
            if (e.target.id === 'modalBackdrop') {
                modalBackdrop.classList.remove('show');
            }
        });
    }

    // 초기 렌더링 실행
    render();
});