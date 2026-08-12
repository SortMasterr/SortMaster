"""
로컬 Docker MongoDB 접속 테스트 (호스트 포트 27020).
Atlas(mongodb+srv)가 아니라 표준 mongodb:// 스킴 + 명시적 포트 사용.
인증 없이 띄운 컨테이너면 DB_USER/DB_PASSWORD는 비워둬도 됨.
"""
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

mongoHost = os.getenv("MONGO_HOST", "localhost")
mongoPort = os.getenv("DB_PORT", "27020")
mongoUser = os.getenv("DB_USER")
mongoPassword = os.getenv("DB_PASSWORD")
mongoDbName = os.getenv("DB_NAME", "sortMaster")

if mongoUser and mongoPassword:
    auth = f"{quote_plus(mongoUser)}:{quote_plus(mongoPassword)}@"
else:
    auth = ""

# authSource를 명시 안 하면 드라이버가 admin DB를 인증 기준으로 삼음 — 계정을
# DB_NAME(예: sortMaster)에 스코프해서 만들었으면 안 넣으면 인증 실패남.
mongoUri = (
    f"mongodb://{auth}{mongoHost}:{mongoPort}/"
    f"?appName=sortMasterDB&authSource={mongoDbName}"
)

client = MongoClient(mongoUri, server_api=ServerApi("1"))
try:
    client.admin.command("ping")
    print("✅ 접속 성공!")
except Exception as e:
    print("❌ 접속 실패:", e)
