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

## 참고
- 로컬 Docker MongoDB 사용 (Atlas 아님 — GPU 서버(L40S)에도 동일하게 Docker로 배포 예정)
- 실제 백엔드는 Motor Repository 계층으로 MongoDB에 연동되어 있다. 이 스크립트들은
  `sortMasterTest` 전용 CRUD/화면 데이터 확인 도구다.
