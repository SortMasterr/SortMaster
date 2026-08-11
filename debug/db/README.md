# DB(로컬 Docker MongoDB) 접속·CRUD 테스트 가이드

## 1. 패키지 설치
```bash
pip install pymongo python-dotenv
```

## 2. `.env` 파일 생성 (⚠️ 프로젝트 루트에 생성, `debug/` 안 아님)
Notion에 공유된 `.env` 값을 그대로 프로젝트 루트에 저장(아래 키 포함돼 있는지 확인):
```
MONGO_HOST=
DB_PORT=27020
DB_USER=ID
DB_PASSWORD=PW
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

```bash
python debug/db/testCrud.py
```

## 참고
- 로컬 Docker MongoDB 사용 (Atlas 아님 — GPU 서버(L40S)에도 동일하게 Docker로 배포 예정)
- 실제 백엔드(Repository 계층) DB 연동은 별도(`infra/checkEnv.py`가 접속 여부만 체크), 이 스크립트들은 순수 CRUD 동작 확인용
