# DB(로컬 Docker MongoDB) 접속·CRUD 테스트 가이드

## 1. 패키지 설치
```bash
pip install pymongo python-dotenv
```

## 2. `.env` 파일 생성 (⚠️ 프로젝트 루트에 생성, `debug/` 안 아님)
`.env.example`과 같은 위치(프로젝트 루트)에 `.env`를 만들고 아래 내용 작성:
```
MONGO_HOST=
MONGO_PORT=27020
MONGO_USER=ID
MONGO_PASSWORD=PW
```

## 3. 접속 테스트 (⚠️ 반드시 프로젝트 루트에서 실행)
```bash
python debug/testDbConnection.py
```
`debug/` 폴더 안에서 실행하면 `.env`를 못 찾습니다 — 루트 디렉터리에서 실행하세요.

`✅ 접속 성공!`이 뜨면 정상. `❌ 접속 실패`가 뜨면:
- Docker Desktop이 켜져 있는지, `docker ps`로 Mongo 컨테이너가 떠 있는지 확인
- 포트가 27020으로 매핑돼 있는지 확인 (`-p 27020:27017`)

## 4. CRUD 테스트
Mongo는 스키마리스라 DB/컬렉션을 미리 만들 필요 없음 — 코드에서 첫 insert 시 자동 생성됨.

```bash
python debug/testCrud.py
```

## 참고
- 로컬 Docker MongoDB 사용 (Atlas 아님 — H100 서버에도 동일하게 Docker로 배포 예정)
- 실제 백엔드(Repository 계층) DB 연동은 별도(`infra/check_env.py`가 접속 여부만 체크), 이 스크립트들은 순수 CRUD 동작 확인용
