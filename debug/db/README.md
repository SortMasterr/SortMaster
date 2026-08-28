# DB(로컬 Docker MongoDB) 접속·CRUD 테스트 가이드

## 1. 패키지 설치
```bash
pip install pymongo python-dotenv
```

## 2. `.env` 파일 생성 (⚠️ 프로젝트 루트에 생성, `debug/` 안 아님)

`testDbConnection.py`는 ping만 수행하므로 접속 확인 대상 값을 사용할 수 있다. 반면
`testCrud.py`와 `seedTestEvents.py`는 문서를 쓰므로 아래 로컬 테스트 설정만 허용한다.
`.env.example`을 복사한 뒤 필요 항목을 조정한다.

```
MONGO_HOST=localhost
DB_PORT=27020
DB_NAME=sortMasterTest
DB_USER=
DB_PASSWORD=
```

## 3. 접속 테스트 (⚠️ 반드시 프로젝트 루트에서 실행)
```bash
python debug/db/testDbConnection.py
```
`debug/` 폴더 안에서 실행하면 `.env`를 못 찾습니다 — 루트 디렉터리에서 실행하세요.

`✅ 접속 성공!`이 뜨면 정상. `❌ 접속 실패`가 뜨면:
- Docker Desktop이 켜져 있는지, `docker ps`로 Mongo 컨테이너가 떠 있는지 확인
- 포트가 27020으로 매핑돼 있는지 확인 (`-p 27020:27017`)

## 4. CRUD 테스트
Mongo는 스키마리스라 DB/컬렉션을 미리 만들 필요 없음 — 코드에서 첫 insert 시 자동 생성됨.

두 쓰기 스크립트는 `MONGO_HOST=localhost`/`127.0.0.1`/`::1`과
`DB_NAME=sortMasterTest` 조합이 아니면 즉시 중단한다. 공유·운영 DB 값을 둔 채 실행해도
쓰기 전에 차단된다.

```bash
python debug/db/testCrud.py
python debug/db/seedTestEvents.py
```

## 5. visitClips 적재 확인 (읽기 전용)

`presenceGateService`가 사람 방문마다 무조건 저장하는 `visitClips` 컬렉션이 실제로
쌓이는지 확인하는 스크립트. `testDbConnection.py`와 동일하게 `.env` 접속 대상을
조회만 하고 아무것도 쓰지 않는다 — 로컬/팀 배포 서버 어느 쪽 `.env`로도 실행 가능.

```bash
python debug/db/checkVisitClips.py
```

전체 문서 수, `matchedEventIds`가 비어있는(재학습 후보) 문서 수, 최근 5개를 출력한다.
`trackIds`/`unresolvedTrackIds`는 GPU `tracking2.py`가 보내는 트랙 신호(EP-15/EP-16)로
채워진다 — 스크립트 쪽 전송은 구현 완료지만 **GPU 서버 실기기에서 실제로 도달하는지는 아직
미검증**이라, 값이 비어 있다고 곧바로 버그는 아니다(`.agentfiles/architecture.md`의
"재학습용 미확정 방문 캡처" 참고).

## 6. visitClip GIF 내려받기 (읽기 전용)

`visitClips`에 저장된 실제 GIF를 GridFS(`topMedia`)에서 로컬 파일로 내려받는다. 조회만
하고 아무것도 쓰지 않는다. 받은 파일은 이미지 뷰어나 브라우저로 열면 된다.

```bash
python debug/db/downloadVisitClipMedia.py
python debug/db/downloadVisitClipMedia.py --imageFileId <objectId 문자열>
```

`--imageFileId`를 생략하면 가장 최근 `visitClip` 문서의 GIF를 받는다.

## 참고
- 로컬 Docker MongoDB 사용 (Atlas 아님 — GPU 서버(L40S)에도 동일하게 Docker로 배포 예정)
- 실제 백엔드는 Motor Repository 계층으로 MongoDB에 연동되어 있다. 이 스크립트들은
  `sortMasterTest` 전용 CRUD/화면 데이터 확인 도구다.
