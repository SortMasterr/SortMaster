# 플레이스홀더 컨테이너 — 실제 학습/파인튜닝 코드가 들어오기 전까지 스캐폴드만 구성.
# 라벨링/학습(YOLOv8 재학습 + Qwen3-VL-8B LoRA·QLoRA 파인튜닝) 코드가 준비되면 내용 채울 것.
# 베이스 이미지의 CUDA 버전은 GPU 서버의 드라이버 버전 확정 후 재검토.
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

WORKDIR /workspace

RUN pip install --no-cache-dir \
        ultralytics \
        transformers \
        peft \
        bitsandbytes \
        accelerate

CMD ["bash"]
