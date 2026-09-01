import cv2
import os
import random

# 이미지 폴더
input_folder = r"C:\final_project\code\images5_brightness"

for filename in os.listdir(input_folder):

    # jpg / jpeg만 처리
    if not filename.lower().endswith((".jpg", ".jpeg")):
        continue

    input_path = os.path.join(input_folder, filename)

    # 이미지 읽기
    image = cv2.imread(input_path)

    if image is None:
        print(f"이미지 읽기 실패: {filename}")
        continue

    # 밝기 범위
    # 어두운 이미지가 조금 더 많이 나오도록 설정
    brightness = random.choice([
        0.7,
        0.7,
        0.8,
        0.8,
        0.9,
        0.9,
        1.0,
        1.1,
        1.2
    ])

    # 밝기 적용
    bright_image = cv2.convertScaleAbs(
        image,
        alpha=brightness,
        beta=0
    )

    # 기존 이미지에 덮어쓰기
    cv2.imwrite(input_path, bright_image)

    print(f"{filename} → 밝기 {brightness}")

print("밝기 증강 및 덮어쓰기 완료!")