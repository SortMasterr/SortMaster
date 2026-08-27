import os
from collections import Counter


def count_yolo_classes(base_path):

    folders = {
        "TRAIN": os.path.join(base_path, "labels", "train"),
        "VAL": os.path.join(base_path, "labels", "val"),
        "TEST": os.path.join(base_path, "labels", "test")
    }

    for folder_name, folder_path in folders.items():

        print("\n" + "=" * 60)
        print(f"{folder_name} 클래스 개수")
        print("=" * 60)

        if not os.path.exists(folder_path):
            print(f"폴더가 없습니다: {folder_path}")
            continue

        class_count = Counter()
        total_txt = 0

        # 4, 5, 6, 7 클래스가 포함된 파일 저장
        special_files = {
            4: [],
            5: [],
            6: [],
            7: []
        }

        # ==========================================
        # TXT 파일 확인
        # ==========================================

        for filename in os.listdir(folder_path):

            if not filename.lower().endswith(".txt"):
                continue

            total_txt += 1

            file_path = os.path.join(folder_path, filename)

            try:

                with open(file_path, "r", encoding="utf-8") as f:

                    for line in f:

                        line = line.strip()

                        if not line:
                            continue

                        # YOLO 형식
                        # class x_center y_center width height
                        parts = line.split()

                        if len(parts) < 5:
                            continue

                        class_id = int(parts[0])

                        # 클래스 개수 증가
                        class_count[class_id] += 1

                        # 4, 5, 6, 7 클래스 파일 찾기
                        if class_id in special_files:
                            special_files[class_id].append(filename)

            except Exception as e:

                print(f"파일 읽기 오류: {filename}")
                print(e)

        # ==========================================
        # 라벨 파일 개수
        # ==========================================

        print(f"\n라벨 파일 수 : {total_txt}개")

        # ==========================================
        # 클래스별 개수
        # ==========================================

        print("\n[ 클래스별 개수 ]")

        # 0~7 클래스 모두 출력
        for class_id in range(8):

            print(f"클래스 {class_id}: {class_count[class_id]}개")

        # ==========================================
        # 전체 클래스 개수
        # ==========================================

        total_class_count = sum(class_count.values())

        print("-" * 40)
        print(f"전체 클래스 개수 : {total_class_count}개")

        # ==========================================
        # 4, 5, 6, 7 클래스 포함 파일
        # ==========================================

        print("\n[ 클래스 4, 5, 6, 7 포함 파일 ]")
        print("-" * 60)

        for class_id in [4, 5, 6, 7]:

            # 같은 파일이 여러 번 들어가는 것 방지
            files = sorted(set(special_files[class_id]))

            print(f"\n클래스 {class_id}: {len(files)}개 파일")

            if files:

                for filename in files:
                    print(f"  - {filename}")

            else:
                print("  없음")


# ==========================================
# 실행
# ==========================================

base_path = r"C:\Users\Woori\Pictures\yolo_dataset_trash"

count_yolo_classes(base_path)