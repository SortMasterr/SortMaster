# GPU 서버에서 SIDE(ELEV-SIDE) MobileNet_V3_Small 상시 추론용 — sideOverflow.py를
# 컨테이너로 감싼 것뿐, FastAPI/uvicorn 없음(TOP의 Dockerfile과 동일한 이유 — 로컬
# 백엔드 MJPEG를 구독해서 판정 결과를 POST로 밀어넣기만 하는 워커).
# training/Dockerfile과 같은 검증된 베이스 이미지 태그 사용(GPU 서버 드라이버
# 595.84/CUDA 13.2와 호환 확인됨).
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        torchvision \
        opencv-python-headless \
        requests \
        numpy

# 소스/가중치(bestSide.pt)/roi.json은 이미지에 굽지 않고 볼륨으로 마운트
# (training/Dockerfile과 같은 패턴 — bestSide.pt는 .gitignore 대상이라 이미지에
# 구우면 재빌드마다 다시 넣어야 해서 번거로움). docker-compose.yml 참고.
CMD ["python", "sideOverflow.py"]
