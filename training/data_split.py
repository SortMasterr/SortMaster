import os
import shutil
import random

def split_yolo_dataset(source_dir, dataset_dir, test_count=200, val_count=100):
    """
    이미지와 TXT 라벨을 랜덤하게 섞은 후
    Test / Val / Train으로 복사하는 함수

    Test : 200장
    Val  : 100장
    Train: 나머지

    원본 images3 파일은 삭제하지 않고 그대로 유지
    """

    # ==========================================
    # 1. 경로 설정
    # ==========================================

    image_source = source_dir
    label_source = source_dir

    image_train = os.path.join(dataset_dir, "images", "train")
    image_val = os.path.join(dataset_dir, "images", "val")
    image_test = os.path.join(dataset_dir, "images", "test")

    label_train = os.path.join(dataset_dir, "labels", "train")
    label_val = os.path.join(dataset_dir, "labels", "val")
    label_test = os.path.join(dataset_dir, "labels", "test")

    # ==========================================
    # 2. 폴더 생성
    # ==========================================

    for folder in [
        image_train, image_val, image_test,
        label_train, label_val, label_test
    ]:
        os.makedirs(folder, exist_ok=True)

    # ==========================================
    # 3. JPG 파일 찾기
    # ==========================================

    image_files = [
        f for f in os.listdir(image_source)
        if f.lower().endswith((".jpg", ".jpeg"))
    ]

    print(f"전체 이미지 개수: {len(image_files)}")

    # ==========================================
    # 4. 랜덤하게 섞기
    # ==========================================

    random.shuffle(image_files)

    print("이미지를 랜덤하게 섞었습니다.")

    # ==========================================
    # 5. 데이터 분할
    # ==========================================

    test_files = image_files[:test_count]

    val_files = image_files[
        test_count:test_count + val_count
    ]

    train_files = image_files[
        test_count + val_count:
    ]

    print()
    print(f"Test  : {len(test_files)}장")
    print(f"Val   : {len(val_files)}장")
    print(f"Train : {len(train_files)}장")

    # ==========================================
    # 6. 이미지 + 라벨 복사 함수
    # ==========================================

    def copy_files(files, image_dest, label_dest):

        for image_file in files:

            # ----------------------------------
            # 이미지 복사
            # ----------------------------------

            image_src = os.path.join(
                image_source,
                image_file
            )

            image_dst = os.path.join(
                image_dest,
                image_file
            )

            shutil.copy2(
                image_src,
                image_dst
            )

            # ----------------------------------
            # 동일한 이름의 TXT 라벨 찾기
            # ----------------------------------

            base_name = os.path.splitext(image_file)[0]

            label_file = base_name + ".txt"

            label_src = os.path.join(
                label_source,
                label_file
            )

            label_dst = os.path.join(
                label_dest,
                label_file
            )

            # ----------------------------------
            # 라벨이 있으면 복사
            # ----------------------------------

            if os.path.exists(label_src):

                shutil.copy2(
                    label_src,
                    label_dst
                )

            else:

                print(f"⚠ 라벨 없음: {label_file}")

    # ==========================================
    # 7. Test 복사
    # ==========================================

    copy_files(
        test_files,
        image_test,
        label_test
    )

    # ==========================================
    # 8. Val 복사
    # ==========================================

    copy_files(
        val_files,
        image_val,
        label_val
    )

    # ==========================================
    # 9. Train 복사
    # ==========================================

    copy_files(
        train_files,
        image_train,
        label_train
    )

    # ==========================================
    # 10. 완료
    # ==========================================

    print()
    print("==========================================")
    print("데이터셋 분배 완료!")
    print("==========================================")

    print(f"Test  이미지 : {image_test}")
    print(f"Test  라벨   : {label_test}")

    print(f"Val   이미지 : {image_val}")
    print(f"Val   라벨   : {label_val}")

    print(f"Train 이미지 : {image_train}")
    print(f"Train 라벨   : {label_train}")


# ==================================================
# 실행
# ==================================================

# split_yolo_dataset(
#     source_dir=r"C:\final_project\code\images3",
#     dataset_dir=r"C:\final_project\yolo_dataset_trash",
#     test_count=200,
#     val_count=100
# )