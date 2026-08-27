"""사람이 브라우저에서 자동 라벨을 검수하고 결정 JSONL을 생성하는 로컬 UI입니다."""
from __future__ import annotations

import json
import os
import threading
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from common.pipelineUtilities import ManifestWriter, iterateManifest


_PAGE = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SortMaster 사람 라벨 검수</title><style>
body{font-family:system-ui,sans-serif;margin:0;background:#111827;color:#e5e7eb}main{max-width:1400px;margin:auto;padding:20px}
header,.controls,.panel{display:flex;gap:12px;align-items:center}.panel{align-items:flex-start}.images{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;flex:3}.images img{width:100%;max-height:620px;object-fit:contain;background:#030712}.form{flex:1;min-width:320px}textarea,input{box-sizing:border-box;width:100%;padding:9px;margin:5px 0 12px;background:#1f2937;color:#fff;border:1px solid #4b5563}textarea{height:180px;font-family:monospace}button{padding:10px 16px;border:0;border-radius:6px;cursor:pointer}.approve{background:#16a34a;color:#fff}.reject{background:#dc2626;color:#fff}.nav{background:#374151;color:#fff}.meta{white-space:pre-wrap;background:#1f2937;padding:10px;max-height:220px;overflow:auto}.saved{color:#86efac}@media(max-width:1100px){.panel{display:block}.images{grid-template-columns:1fr}.form{min-width:0}}
</style></head><body><main>
<header><h2>SortMaster 사람 라벨 검수</h2><span id="progress"></span><span id="saved" class="saved"></span></header>
<div class="controls"><button class="nav" onclick="move(-1)">이전</button><button class="nav" onclick="move(1)">다음</button><button class="nav" onclick="goUndecided()">미검수로 이동</button></div>
<div class="panel"><div class="images"><figure><figcaption>원본</figcaption><img id="original"></figure><figure><figcaption>YOLO bbox</figcaption><img id="annotated"></figure><figure><figcaption>Qwen 라벨링</figcaption><img id="qwen"></figure></div>
<section class="form"><div id="meta" class="meta"></div><label>YOLO 라벨 (classId centerX centerY width height)</label><textarea id="label"></textarea><label>검수자</label><input id="reviewer"><label>메모</label><textarea id="notes" style="height:90px"></textarea><button class="approve" onclick="save('approved')">승인 / 수정 승인</button> <button class="reject" onclick="save('rejected')">거절</button></section></div>
<script>
let index=0,total=0,current=null,waitTimer=null;
async function summary(){const s=await (await fetch('/api/summary')).json();total=s.total;document.getElementById('saved').textContent=`완료 ${s.decided}/${s.total} (LLM이 계속 만드는 중일 수 있음)`;return s}
function stopWaiting(){if(waitTimer!==null){clearTimeout(waitTimer);waitTimer=null}}
async function waitForIndex(i){
    document.getElementById('progress').textContent='다음 항목을 기다리는 중... (LLM 처리 중)';
    return new Promise((resolve)=>{
        const check=async()=>{
            const s=await summary();
            if(i<s.total){stopWaiting();resolve();return}
            waitTimer=setTimeout(check,2000);
        };
        check();
    });
}
async function load(i){
    if(!total)await summary();
    if(i>=total)await waitForIndex(i);
    stopWaiting();
    index=Math.max(0,i);
    current=await (await fetch('/api/item?index='+index)).json();
    document.getElementById('progress').textContent=`${index+1} / ${total}`;
    document.getElementById('original').src=`/media?id=${encodeURIComponent(current.id)}&kind=original&t=${Date.now()}`;
    document.getElementById('annotated').src=`/media?id=${encodeURIComponent(current.id)}&kind=annotated&t=${Date.now()}`;
    document.getElementById('qwen').src=`/media?id=${encodeURIComponent(current.id)}&kind=qwen&t=${Date.now()}`;
    document.getElementById('label').value=current.labelText;
    document.getElementById('reviewer').value=current.decision?.reviewer||'';
    document.getElementById('notes').value=current.decision?.notes||'';
    document.getElementById('meta').textContent=JSON.stringify({id:current.id,video:current.video,qwen:current.review,classes:current.classes,previousDecision:current.decision?.decision||null},null,2);
}
function move(step){load(index+step)}
async function goUndecided(){const s=await summary();load(s.firstUndecidedIndex<0?s.total:s.firstUndecidedIndex)}
async function save(decision){const body={id:current.id,decision,reviewer:document.getElementById('reviewer').value.trim(),notes:document.getElementById('notes').value,labelText:document.getElementById('label').value};const response=await fetch('/api/decision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await response.json();if(!response.ok){alert(result.error||'저장 실패');return}if(result.complete){document.getElementById('saved').textContent='완료 '+total+'/'+total+' — 파이프라인을 계속 실행합니다.';return}await summary();load(index+1)}
summary().then(()=>goUndecided()).catch(e=>alert(e));
setInterval(()=>{if(waitTimer===null)summary()},5000);
</script></main></body></html>'''


class HumanReviewUiStage:
    """큐와 결정 파일을 연결하는 localhost 전용 검수 웹 서버입니다."""

    def _validateLabelText(self, labelText: str) -> str:
        """수정된 YOLO 라벨의 클래스와 정규화 좌표를 저장 전에 검증합니다."""
        classCount = len(self.config["dataset"]["classes"])
        normalizedLines: list[str] = []
        for lineNumber, line in enumerate(labelText.splitlines(), 1):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) != 5:
                raise ValueError(f"라벨 {lineNumber}행은 값이 5개여야 합니다.")
            try:
                classId = int(parts[0])
                coordinates = [float(value) for value in parts[1:]]
            except ValueError as error:
                raise ValueError(f"라벨 {lineNumber}행에 숫자가 아닌 값이 있습니다.") from error
            if not 0 <= classId < classCount:
                raise ValueError(f"라벨 {lineNumber}행 classId 범위 오류: {classId}")
            if not all(0.0 <= value <= 1.0 for value in coordinates):
                raise ValueError(f"라벨 {lineNumber}행 좌표는 0~1이어야 합니다.")
            normalizedLines.append(f"{classId} " + " ".join(f"{value:.6f}" for value in coordinates))
        return "\n".join(normalizedLines) + ("\n" if normalizedLines else "")

    def launchHumanReviewUi(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        openBrowser: bool = True,
        stopWhenComplete: bool = False,
    ) -> None:
        """검수 큐를 제공한다.

        review 단계가 아직 진행 중이어도(humanReviewQueue.jsonl에 항목이 계속
        추가되는 중이어도) 시작할 수 있다 — 큐가 비어 있으면 새 항목이 도착할
        때까지 대기 안내만 보여준다. `_reloadQueue`가 매 요청마다 파일을 다시
        읽어 새로 도착한 항목을 반영하므로 서버 재시작 없이 실시간으로 늘어난다.
        """
        if not 1 <= port <= 65535:
            raise ValueError("review UI port는 1~65535 범위여야 합니다.")

        queueRows: list[dict[str, Any]] = []
        queueById: dict[str, dict[str, Any]] = {}
        decisions = {
            str(row["id"]): row
            for row in iterateManifest(self.humanDecisionsManifest)
        }
        correctedRoot = self.humanReviewRoot / "correctedLabels"
        writeLock = threading.Lock()
        stage = self

        def reloadQueue() -> None:
            # humanReviewQueue.jsonl은 review 단계가 항목을 처리할 때마다 바로
            # append하므로(원자적 전체 교체가 아님), 새로 늘어난 줄만 반영한다.
            with writeLock:
                for row in iterateManifest(stage.humanReviewQueue):
                    rowId = str(row["id"])
                    if rowId not in queueById:
                        queueRows.append(row)
                        queueById[rowId] = row

        reloadQueue()
        if stopWhenComplete and queueById and all(itemId in decisions for itemId in queueById):
            print("[HUMAN REVIEW UI] 모든 결정이 이미 저장되어 다음 단계를 계속합니다.")
            return

        def persistDecisions() -> None:
            # 파일을 매 요청마다 원자적으로 다시 만들면 브라우저/프로세스 종료 중에도 이전 결정이 보존된다.
            with ManifestWriter(stage.humanDecisionsManifest) as writer:
                for row in queueRows:
                    decision = decisions.get(str(row["id"]))
                    if decision is not None:
                        writer.write(decision)

        class ReviewHandler(BaseHTTPRequestHandler):
            def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
                payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                if parsed.path == "/":
                    payload = _PAGE.encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers(); self.wfile.write(payload); return
                if parsed.path == "/api/summary":
                    reloadQueue()
                    undecided = next((i for i,row in enumerate(queueRows) if str(row["id"]) not in decisions), -1)
                    self._json({"total": len(queueRows), "decided": len(decisions), "firstUndecidedIndex": undecided}); return
                if parsed.path == "/api/item":
                    reloadQueue()
                    try: row = queueRows[int(query.get("index", ["0"])[0])]
                    except (ValueError, IndexError): self._json({"error":"잘못된 index"},HTTPStatus.BAD_REQUEST); return
                    itemId = str(row["id"]); decision = decisions.get(itemId)
                    labelPath = Path((decision or {}).get("labelPath") or row["labelPath"])
                    self._json({"id":itemId,"video":row.get("video"),"review":row.get("review"),"classes":stage.config["dataset"]["classes"],"decision":decision,"labelText":labelPath.read_text(encoding="utf-8")}); return
                if parsed.path == "/media":
                    itemId=query.get("id",[""])[0]; kind=query.get("kind",[""])[0]; row=queueById.get(itemId)
                    if row is None or kind not in {"original","annotated","qwen"}: self.send_error(HTTPStatus.NOT_FOUND); return
                    mediaKey={"original":"imagePath","annotated":"annotatedPath","qwen":"qwenAnnotatedPath"}[kind]
                    mediaPath=Path(row[mediaKey])
                    if not mediaPath.is_file(): self.send_error(HTTPStatus.NOT_FOUND); return
                    payload=mediaPath.read_bytes(); self.send_response(HTTPStatus.OK); self.send_header("Content-Type","image/jpeg"); self.send_header("Content-Length",str(len(payload))); self.end_headers(); self.wfile.write(payload); return
                self.send_error(HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                if urlparse(self.path).path != "/api/decision": self.send_error(HTTPStatus.NOT_FOUND); return
                try:
                    length=int(self.headers.get("Content-Length","0")); body=json.loads(self.rfile.read(length)); itemId=str(body.get("id","")); decision=str(body.get("decision",""))
                    if itemId not in queueById: raise ValueError("현재 큐에 없는 id입니다.")
                    if decision not in {"approved","rejected"}: raise ValueError("approved/rejected만 허용합니다.")
                    output={"id":itemId,"decision":decision,"reviewer":str(body.get("reviewer","")).strip(),"reviewedAt":datetime.now(timezone.utc).isoformat(),"notes":str(body.get("notes","")).strip()}
                    if decision == "approved":
                        labelText=stage._validateLabelText(str(body.get("labelText",""))); original=Path(queueById[itemId]["labelPath"]).read_text(encoding="utf-8")
                        if labelText != original:
                            correctedPath=correctedRoot/f"{itemId}.txt"; correctedPath.parent.mkdir(parents=True,exist_ok=True); temporaryPath=correctedPath.with_suffix(".txt.tmp")
                            temporaryPath.write_text(labelText,encoding="utf-8"); os.replace(temporaryPath,correctedPath); output["labelPath"]=str(correctedPath.resolve())
                    with writeLock:
                        decisions[itemId] = output
                        persistDecisions()
                        complete = all(queueId in decisions for queueId in queueById)
                    self._json({"saved": True, "complete": complete})
                    if complete and stopWhenComplete:
                        threading.Thread(target=server.shutdown, daemon=True).start()
                except (ValueError,KeyError,json.JSONDecodeError,OSError) as error: self._json({"error":str(error)},HTTPStatus.BAD_REQUEST)

            def log_message(self, format: str, *args: Any) -> None:
                return

        server = ThreadingHTTPServer((host, port), ReviewHandler)
        url = f"http://{host}:{port}"
        stopMessage = "모든 검수 완료 시 자동 종료" if stopWhenComplete else "종료: Ctrl+C"
        print(f"[HUMAN REVIEW UI] {url} ({stopMessage})")
        if openBrowser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n[HUMAN REVIEW UI] 종료")
        finally:
            server.server_close()
        if stopWhenComplete and not all(itemId in decisions for itemId in queueById):
            raise RuntimeError("사람 검수가 완료되기 전에 검수 UI가 종료됐습니다.")
