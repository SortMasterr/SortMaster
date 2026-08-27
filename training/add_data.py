import os
import shutil
import random
from pathlib import Path

def split_cupholder(folder_path):

    # ==============================
    # 저장할 폴더 경로
    # ==============================
    train_img = r"C:\Users\Woori\Pictures\yolo_dataset_trash\images\train"
    train_label = r"C:\Users\Woori\Pictures\yolo_dataset_trash\labels\train"

    val_img = r"C:\Users\Woori\Pictures\yolo_dataset_trash\images\val"
    val_label = r"C:\Users\Woori\Pictures\yolo_dataset_trash\labels\val"

    test_img = r"C:\Users\Woori\Pictures\yolo_dataset_trash\images\test"
    test_label = r"C:\Users\Woori\Pictures\yolo_dataset_trash\labels\test"


    # ==============================
    # 저장 폴더가 없으면 생성
    # ==============================
    os.makedirs(train_img, exist_ok=True)
    os.makedirs(train_label, exist_ok=True)

    os.makedirs(val_img, exist_ok=True)
    os.makedirs(val_label, exist_ok=True)

    os.makedirs(test_img, exist_ok=True)
    os.makedirs(test_label, exist_ok=True)


    # ==============================
    # jpg 파일만 가져오기
    # ==============================
    jpg_files = []

    for filename in os.listdir(folder_path):

        if filename.lower().endswith(".jpg"):

            # jpg와 이름이 같은 txt가 있는지 확인
            txt_name = os.path.splitext(filename)[0] + ".txt"
            txt_path = os.path.join(folder_path, txt_name)

            # jpg + txt가 한 쌍인 경우만 추가
            if os.path.exists(txt_path):
                jpg_files.append(filename)


    print(f"jpg + txt 한쌍: {len(jpg_files)}개")


    # ==============================
    # 랜덤으로 섞기
    # ==============================
    random.shuffle(jpg_files)


    # ==============================
    # 370 / 46 / 47개로 분리
    # ==============================
    train_files = jpg_files[:370]

    val_files = jpg_files[370:370 + 46]

    test_files = jpg_files[370 + 46:370 + 46 + 47]


    print(f"Train : {len(train_files)}개")
    print(f"Val   : {len(val_files)}개")
    print(f"Test  : {len(test_files)}개")


    # ==============================
    # 복사 함수
    # ==============================
    def copy_files(file_list, img_folder, label_folder):

        for jpg_name in file_list:

            # jpg 경로
            jpg_src = os.path.join(folder_path, jpg_name)

            # txt 파일명
            txt_name = os.path.splitext(jpg_name)[0] + ".txt"

            # txt 경로
            txt_src = os.path.join(folder_path, txt_name)


            # 최종 복사 위치
            jpg_dst = os.path.join(img_folder, jpg_name)
            txt_dst = os.path.join(label_folder, txt_name)


            # jpg 복사
            shutil.copy2(jpg_src, jpg_dst)

            # txt 복사
            shutil.copy2(txt_src, txt_dst)


    # ==============================
    # Train 복사
    # ==============================
    copy_files(
        train_files,
        train_img,
        train_label
    )


    # ==============================
    # Val 복사
    # ==============================
    copy_files(
        val_files,
        val_img,
        val_label
    )


    # ==============================
    # Test 복사
    # ==============================
    copy_files(
        test_files,
        test_img,
        test_label
    )


    print("\n복사 완료!")





def add_train_data(source_folder):
    image_folder = r"C:\Users\Woori\Pictures\yolo_dataset_trash\images\train"
    label_folder = r"C:\Users\Woori\Pictures\yolo_dataset_trash\labels\train"

    # 대상 폴더가 없으면 생성
    os.makedirs(image_folder, exist_ok=True)
    os.makedirs(label_folder, exist_ok=True)

    # source_folder의 파일 확인
    for filename in os.listdir(source_folder):
        source_path = os.path.join(source_folder, filename)

        # JPG 이미지 → images/train
        if filename.lower().endswith(".jpg"):
            shutil.copy2(
                source_path,
                os.path.join(image_folder, filename)
            )

        # TXT 라벨 → labels/train
        elif filename.lower().endswith(".txt"):
            shutil.copy2(
                source_path,
                os.path.join(label_folder, filename)
            )

    print("복사 완료!")

def copy_trash_train_data(
    source_dir=r"C:\final_project\code\images2_검수완료",
    image_dst=r"C:\final_project\yolo_dataset_trash\images\train",
    label_dst=r"C:\final_project\yolo_dataset_trash\labels\train"
):
    # ==========================================
    # 1. 목적지 폴더 생성
    # ==========================================
    os.makedirs(image_dst, exist_ok=True)
    os.makedirs(label_dst, exist_ok=True)

    copied_count = 0
    skipped_count = 0

    # ==========================================
    # 2. source 폴더의 파일 확인
    # ==========================================
    for filename in os.listdir(source_dir):

        # JPG 이미지만 확인
        if not filename.lower().endswith(".jpg"):
            continue

        # 확장자 제거
        name = os.path.splitext(filename)[0]

        # trash_2011부터 시작하는 파일만
        if not name.startswith("trash_"):
            continue

        # 숫자 부분 확인
        try:
            number = int(name.split("_")[1])
        except (ValueError, IndexError):
            continue

        # trash_2011 이전 파일 제외
        if number < 2011:
            continue

        # ==========================================
        # 3. 이미지 파일 경로
        # ==========================================
        image_src = os.path.join(source_dir, filename)

        # ==========================================
        # 4. 같은 이름의 txt 라벨 파일
        # ==========================================
        label_filename = name + ".txt"
        label_src = os.path.join(source_dir, label_filename)

        # ==========================================
        # 5. 라벨 파일이 없으면 건너뜀
        # ==========================================
        if not os.path.exists(label_src):
            print(f"[SKIP] 라벨 없음: {label_filename}")
            skipped_count += 1
            continue

        # ==========================================
        # 6. 이미지 복사
        # ==========================================
        shutil.copy2(
            image_src,
            os.path.join(image_dst, filename)
        )

        # ==========================================
        # 7. 라벨 복사
        # ==========================================
        shutil.copy2(
            label_src,
            os.path.join(label_dst, label_filename)
        )

        copied_count += 1

        print(f"[COPY] {filename} + {label_filename}")

    # ==========================================
    # 8. 결과 출력
    # ==========================================
    print("\n===================================")
    print("복사 완료!")
    print(f"복사된 데이터 : {copied_count}개")
    print(f"건너뛴 데이터 : {skipped_count}개")
    print("===================================")

