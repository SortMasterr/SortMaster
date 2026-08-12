# 팀 공용 학습 환경 — JupyterLab으로 여러 명이 같이 접속해서 YOLOv8 재학습/
# Qwen3-VL-8B LoRA·QLoRA 파인튜닝 진행. 라벨링/학습 코드가 준비되면 /workspace(볼륨
# 마운트된 training/ 디렉터리)에 채울 것.
# 베이스 이미지 CUDA 12.4는 GPU 서버 드라이버(595.84, CUDA 13.2)와 호환 확인됨(하위 호환).
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

WORKDIR /workspace

RUN pip install --no-cache-dir \
        ultralytics \
        transformers \
        peft \
        bitsandbytes \
        accelerate \
        "jupyterlab==4.3.4"

EXPOSE 8888

# JUPYTER_TOKEN은 .env에서 주입(커밋 금지, 팀원끼리만 공유). 컨테이너 root는
# rootless Docker의 유저 네임스페이스 덕분에 호스트에서는 비특권 사용자로 매핑되므로
# --allow-root가 호스트 보안에 영향 없음.
CMD ["sh", "-c", "jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root --ServerApp.token=\"$JUPYTER_TOKEN\" --ServerApp.root_dir=/workspace"]
