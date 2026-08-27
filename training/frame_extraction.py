import cv2
import os

# ==========================================
# 1. 경로 설정
# ==========================================

# 영상 파일 경로
video_path = r"C:\final_project\video\trash_video.mp4"

# 추출한 이미지를 저장할 폴더
output_dir = r"C:\final_project\code\images"

# 몇 초마다 이미지 1장을 추출할지
extract_interval_seconds = 0.3


# ==========================================
# 2. 이미지 저장 폴더 생성
# ==========================================

os.makedirs(output_dir, exist_ok=True)


# ==========================================
# 3. 영상 열기
# ==========================================

cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print("❌ 영상을 열 수 없습니다.")
    print("영상 경로를 확인하세요.")
    exit()


# ==========================================
# 4. 영상 정보 가져오기
# ==========================================

fps = cap.get(cv2.CAP_PROP_FPS)

total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

video_seconds = total_frames / fps


print("=" * 50)
print("영상 정보")
print("=" * 50)

print(f"FPS : {fps}")
print(f"해상도 : {video_width} x {video_height}")
print(f"전체 프레임 : {total_frames}")
print(f"영상 길이 : {video_seconds:.2f}초")

print("=" * 50)


# ==========================================
# 5. 몇 프레임마다 저장할지 계산
# ==========================================

frame_interval = int(fps * extract_interval_seconds)

print(f"{extract_interval_seconds}초마다 이미지 1장 추출")
print(f"{frame_interval} 프레임마다 저장")


# ==========================================
# 6. 프레임 추출
# ==========================================

frame_count = 0
image_count = 0

while True:

    # 영상에서 프레임 하나 읽기
    ret, frame = cap.read()

    # 영상이 끝났으면 종료
    if not ret:
        break

    # 지정한 간격마다 이미지 저장
    if frame_count % frame_interval == 0:

        # 파일 이름
        filename = os.path.join(
            output_dir,
            f"trash_{image_count + 1:04d}.jpg"
        )

        # JPG로 저장
        cv2.imwrite(filename, frame)

        image_count += 1

        print(f"저장 완료: {filename}")

    frame_count += 1


# ==========================================
# 7. 종료
# ==========================================

cap.release()

print()
print("=" * 50)
print("✅ 이미지 추출 완료!")
print("=" * 50)
print(f"총 {image_count}장의 이미지가 생성되었습니다.")
print(f"저장 위치 : {output_dir}")