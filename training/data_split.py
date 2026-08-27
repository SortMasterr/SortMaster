import os
import shutil
import random



## 초기에는 val: 10, test: 20으로 설정되어 있었음
def split_yolo_dataset(
    dataset_dir,
    val_count=10,
    test_count=20,
    seed=42
):
    # =========================================================
    # 1. YOLO 데이터셋 폴더
    # =========================================================
    train_img_dir = os.path.join(dataset_dir, "images", "train")
    val_img_dir = os.path.join(dataset_dir, "images", "val")
    test_img_dir = os.path.join(dataset_dir, "images", "test")

    train_label_dir = os.path.join(dataset_dir, "labels", "train")
    val_label_dir = os.path.join(dataset_dir, "labels", "val")
    test_label_dir = os.path.join(dataset_dir, "labels", "test")

    # =========================================================
    # 2. Val / Test 폴더 생성
    # =========================================================
    os.makedirs(val_img_dir, exist_ok=True)
    os.makedirs(test_img_dir, exist_ok=True)

    os.makedirs(val_label_dir, exist_ok=True)
    os.makedirs(test_label_dir, exist_ok=True)

    # =========================================================
    # 3. Train 이미지 가져오기
    # =========================================================
    image_extensions = {".jpg", ".jpeg", ".png"}

    train_images = []

    for file in os.listdir(train_img_dir):
        ext = os.path.splitext(file)[1].lower()

        if ext in image_extensions:
            train_images.append(file)

    print("현재 Train 이미지:", len(train_images))

    # =========================================================
    # 4. 데이터가 충분한지 확인
    # =========================================================
    required_count = val_count + test_count

    if len(train_images) < required_count:
        print(
            f"⚠️ Train 이미지가 부족합니다. "
            f"(필요: {required_count}장 / 현재: {len(train_images)}장)"
        )
        return

    # =========================================================
    # 5. 랜덤하게 섞기
    # =========================================================
    random.seed(seed)
    random.shuffle(train_images)

    # =========================================================
    # 6. Val / Test 이미지 선택
    # =========================================================
    move_to_val = train_images[:val_count]

    move_to_test = train_images[
        val_count:val_count + test_count
    ]

    # =========================================================
    # 7. 이미지 + 라벨 이동 함수
    # =========================================================
    def move_dataset(
        image_list,
        src_img_dir,
        src_label_dir,
        dst_img_dir,
        dst_label_dir
    ):
        for image_file in image_list:

            # 이미지 이름
            image_name = os.path.splitext(image_file)[0]

            # 이미지 경로
            image_src = os.path.join(
                src_img_dir,
                image_file
            )

            image_dst = os.path.join(
                dst_img_dir,
                image_file
            )

            # 라벨 경로
            label_file = image_name + ".txt"

            label_src = os.path.join(
                src_label_dir,
                label_file
            )

            label_dst = os.path.join(
                dst_label_dir,
                label_file
            )

            # 이미지 이동
            shutil.move(
                image_src,
                image_dst
            )

            # 라벨 이동
            if os.path.exists(label_src):

                shutil.move(
                    label_src,
                    label_dst
                )

            else:
                print("⚠️ 라벨 없음:", image_file)

    # =========================================================
    # 8. Train → Val 이동
    # =========================================================
    move_dataset(
        move_to_val,
        train_img_dir,
        train_label_dir,
        val_img_dir,
        val_label_dir
    )

    # =========================================================
    # 9. Train → Test 이동
    # =========================================================
    move_dataset(
        move_to_test,
        train_img_dir,
        train_label_dir,
        test_img_dir,
        test_label_dir
    )

    # =========================================================
    # 10. 이미지 개수 확인 함수
    # =========================================================
    def count_images(folder):

        count = 0

        for file in os.listdir(folder):

            ext = os.path.splitext(file)[1].lower()

            if ext in image_extensions:
                count += 1

        return count

    # =========================================================
    # 11. 결과 출력
    # =========================================================
    print()
    print("=" * 50)
    print("데이터셋 분배 완료")
    print("=" * 50)

    print("Train :", count_images(train_img_dir))
    print("Val   :", count_images(val_img_dir))
    print("Test  :", count_images(test_img_dir))


## val:100 test:200장으로 늘림

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