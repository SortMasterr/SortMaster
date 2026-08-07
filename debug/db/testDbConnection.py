"""
로컬 Docker MongoDB 접속 테스트 (호스트 포트 27020).
Atlas(mongodb+srv)가 아니라 표준 mongodb:// 스킴 + 명시적 포트 사용.
인증 없이 띄운 컨테이너면 MONGO_USER/MONGO_PASSWORD는 비워둬도 됨.
"""
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

mongoHost = os.getenv("MONGO_HOST", "localhost")
mongoPort = os.getenv("MONGO_PORT", "27020")
mongoUser = os.getenv("MONGO_USER")
mongoPassword = os.getenv("MONGO_PASSWORD")

if mongoUser and mongoPassword:
    auth = f"{quote_plus(mongoUser)}:{quote_plus(mongoPassword)}@"
else:
    auth = ""

mongoUri = f"mongodb://{auth}{mongoHost}:{mongoPort}/?appName=sortMasterDB"

client = MongoClient(mongoUri, server_api=ServerApi("1"))
try:
    client.admin.command("ping")
    print("✅ 접속 성공!")
except Exception as e:
    print("❌ 접속 실패:", e)
