import cv2
import os
import random

folder_path = r"C:\final_project\code\images5_blur"

for filename in os.listdir(folder_path):

    if not filename.lower().endswith((".jpg", ".jpeg")):
        continue

    image_path = os.path.join(folder_path, filename)

    image = cv2.imread(image_path)

    if image is None:
        continue

    # 랜덤 Blur 강도
    kernel_size = random.choice([5, 7, 9, 11, 13])

    blurred = cv2.GaussianBlur(
        image,
        (kernel_size, kernel_size),
        0
    )

    cv2.imwrite(image_path, blurred)

    print(f"{filename} → Blur ({kernel_size}, {kernel_size})")

print("랜덤 Blur 처리 완료!")