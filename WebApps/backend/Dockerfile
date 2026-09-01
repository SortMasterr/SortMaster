FROM python:3.11-slim

WORKDIR /app

# libgl1/libglib2.0-0: opencv-python 런타임 의존 라이브러리(로컬 웹캠 경로 + 사람 존재
# 감지 detection/presenceDetector.py용, RTSP는 아래 ffmpeg로 처리해서 opencv-python 자체는
# 못 뺌). models/ 아래 추론 스크립트는 GPU 서버에서 별도로 돌아 이 이미지와 무관하다.
# ffmpeg: RTSP 카메라 디코딩용 — OpenCV 내장 ffmpeg가 손상된 H264 프레임에서 파이썬이
# 못 잡는 네이티브 크래시를 내서(streaming/cameraManager.py 참고), 별도 프로세스로
# 격리하기 위해 진짜 ffmpeg 바이너리를 서브프로세스로 띄움.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 패키지 목록 원천은 infra/checkEnv.py의 requiredPackages — 패키지 추가/변경 시 그쪽도 같이 수정.
# 단 pytest는 개발/테스트 전용이라 런타임 이미지에는 넣지 않는다(의도적 차이).
RUN pip install --no-cache-dir \
        "fastapi==0.141.1" \
        "uvicorn[standard]==0.52.1" \
        "pydantic==2.13.4" \
        "pydantic-settings==2.15.0" \
        "motor==3.7.1" \
        "pymongo==4.9.2" \
        "python-multipart==0.0.32" \
        "opencv-python==4.14.0.94" \
        "Pillow==11.1.0" \
        "jinja2==3.1.6" \
        "python-dotenv==1.2.2" \
        "tzdata==2025.2"

# 백엔드는 통계 보고서 발송 시 루트의 RPAs/reportAutomation을 런타임 의존성으로
# import한다. 저장소 루트를 build context로 사용하고 필요한 두 경로만 이미지에 복사한다.
COPY WebApps/backend/ .
COPY RPAs/ ./RPAs/

EXPOSE 8047

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8047"]
