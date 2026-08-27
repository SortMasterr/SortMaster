from ultralytics import YOLO
import os
import glob

# ==========================================
# 1. 경로 설정
# ==========================================

MODEL_PATH = r"C:\final_project\model_result\trash_yolo26n_aug\trash_yolo26n_aug\weights\best.pt"

IMAGE_DIR = r"C:\final_project\code\images5"

LABEL_DIR = r"C:\final_project\code\labels5"


# ==========================================
# 2. labels 폴더 생성
# ==========================================

os.makedirs(LABEL_DIR, exist_ok=True)


# ==========================================
# 3. YOLO 모델 불러오기
# ==========================================

model = YOLO(MODEL_PATH)


# ==========================================
# 4. 이미지 목록 가져오기
# ==========================================

image_files = glob.glob(os.path.join(IMAGE_DIR, "*.jpg"))

print("자동 라벨링할 이미지:", len(image_files))


# ==========================================
# 5. 이미지 하나씩 자동 라벨링
# ==========================================

for image_path in image_files:

    # YOLO 탐지
    results = model.predict(
        source=image_path,
        conf=0.5,
        verbose=False
    )

    result = results[0]

    # 이미지 파일 이름
    image_name = os.path.splitext(
        os.path.basename(image_path)
    )[0]

    # txt 저장 경로
    txt_path = os.path.join(
        LABEL_DIR,
        image_name + ".txt"
    )

    # ======================================
    # 6. YOLO txt 파일 생성
    # ======================================

    with open(txt_path, "w") as f:

        for box in result.boxes:

            # 클래스 번호
            class_id = int(box.cls[0])

            # YOLO 형식으로 변환된 좌표
            x_center, y_center, width, height = box.xywhn[0].tolist()

            # txt 저장
            f.write(
                f"{class_id} "
                f"{x_center:.6f} "
                f"{y_center:.6f} "
                f"{width:.6f} "
                f"{height:.6f}\n"
            )

    print(f"완료: {image_name}.txt")


print("\n============================")
print("✅ 자동 라벨링 완료!")
print("============================")