# DB(MongoDB Atlas) 접속·CRUD 테스트 가이드

## 1. 패키지 설치
```bash
pip install pymongo python-dotenv
```

## 2. `.env` 파일 생성 (⚠️ 프로젝트 루트에 생성, `debug/` 안 아님)
`.env.example`과 같은 위치(프로젝트 루트)에 `.env`를 만들고 아래 내용 작성:
```
MONGO_USER=본인아이디
MONGO_PASSWORD=본인비번
MONGO_HOST=sortmasterdb.0y5ba83.mongodb.net
```
- 아이디/비번은 Atlas → Database Access에서 발급받은 본인 계정 정보

## 3. 접속 테스트 (⚠️ 반드시 프로젝트 루트에서 실행)
```bash
python debug/test_db_connection.py
```
`debug/` 폴더 안에서 실행하면 `.env`를 못 찾습니다 — 루트 디렉터리에서 실행하세요.

### `debug/test_db_connection.py`
`✅ 접속 성공!`이 뜨면 정상. `❌ 접속 실패`가 뜨면 CTO에게 문의

## 4. CRUD 테스트
Atlas 콘솔에서 DB/컬렉션을 미리 만들 필요 없음 — MongoDB는 스키마리스라 코드에서 첫 insert 시 자동 생성됨.

```bash
python debug/test_crud.py
```

### `debug/test_crud.py`

결과는 Atlas 콘솔 → **Data Explorer**(데이터 탐색기)에서도 실시간으로 확인 가능.

## 참고
- 로컬 Docker MongoDB 사용하지 않음 — Atlas로 전환됨
- 실제 백엔드(Repository 계층) DB 연동은 아직 보류(Mock) 상태이며, 이 스크립트들은 순수 계정/CRUD 동작 확인용
