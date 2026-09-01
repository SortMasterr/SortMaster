"""
visitClips에 저장된 실제 GIF를 GridFS(topMedia)에서 로컬 파일로 내려받는 읽기 전용 스크립트.

--imageFileId를 안 주면 가장 최근 visitClip 문서의 GIF를 받는다. 받은 파일은 아무 이미지
뷰어/브라우저로 열어보면 된다(움직이는 GIF).

python debug/db/downloadVisitClipMedia.py
python debug/db/downloadVisitClipMedia.py --imageFileId <objectId 문자열>
"""
import argparse
import os
from urllib.parse import quote_plus

import gridfs
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

mongoHost = os.getenv("MONGO_HOST", "localhost")
mongoPort = os.getenv("DB_PORT", "27020")
mongoUser = os.getenv("DB_USER")
mongoPassword = os.getenv("DB_PASSWORD")
mongoDbName = os.getenv("DB_NAME", "sortMaster")

auth = f"{quote_plus(mongoUser)}:{quote_plus(mongoPassword)}@" if mongoUser and mongoPassword else ""
mongoUri = (
    f"mongodb://{auth}{mongoHost}:{mongoPort}/"
    f"?appName=downloadVisitClipMedia&authSource={mongoDbName}"
)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--imageFileId", default=None, help="GridFS ObjectId 문자열(생략 시 최신 visitClip)")
parser.add_argument("--outDir", default="debug/db/downloads", help="저장 폴더")
args = parser.parse_args()

client = MongoClient(mongoUri, serverSelectionTimeoutMS=5000)
db = client[mongoDbName]

if args.imageFileId:
    imageFileId = args.imageFileId
else:
    latestClip = db.visitClips.find_one({}, sort=[("startedAt", -1)])
    if latestClip is None:
        raise SystemExit("visitClips에 문서가 하나도 없습니다. 먼저 방문을 하나 만들어보세요.")
    imageFileId = latestClip["imageFileId"]
    print(f"최신 visitClip 사용: startedAt={latestClip['startedAt']}, imageFileId={imageFileId}")

fs = gridfs.GridFSBucket(db, bucket_name="topMedia")
gridOutFile = fs.open_download_stream(ObjectId(imageFileId))
gifBytes = gridOutFile.read()

os.makedirs(args.outDir, exist_ok=True)
outputPath = os.path.join(args.outDir, f"{imageFileId}.gif")
with open(outputPath, "wb") as outputFile:
    outputFile.write(gifBytes)

print(f"저장 완료: {outputPath} ({len(gifBytes)} bytes)")
print("아무 이미지 뷰어나 브라우저로 열어서 확인하세요.")

client.close()
