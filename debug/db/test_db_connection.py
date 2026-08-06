from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from urllib.parse import quote_plus
from dotenv import load_dotenv
import os

load_dotenv()
username = quote_plus(os.getenv("MONGO_USER"))
password = quote_plus(os.getenv("MONGO_PASSWORD"))
host = os.getenv("MONGO_HOST")  # sortmasterdb.0y5ba83.mongodb.net

MONGO_URI = f"mongodb+srv://{username}:{password}@{host}/?appName=sortMasterDB"

client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
try:
    client.admin.command("ping")
    print("✅ 접속 성공!")
except Exception as e:
    print("❌ 접속 실패:", e)