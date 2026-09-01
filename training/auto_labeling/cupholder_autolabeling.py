"""Draw one fixed bounding box and append it to every YOLO label file."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

import cv2


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="대표 이미지에서 그린 박스를 같은 폴더의 모든 YOLO 라벨에 추가합니다."
    )
    parser.add_argument("folder", nargs="?", type=Path, default=Path(r"C:\final_project\test"))
    parser.add_argument("--image", type=Path, help="박스를 그릴 대표 이미지 (기본: 첫 이미지)")
    parser.add_argument("--class-id", type=int, help="추가할 YOLO 클래스 ID")
    parser.add_argument("--yes", action="store_true", help="좌표 확인 질문을 생략")
    parser.add_argument("--no-backup", action="store_true", help="라벨 백업을 만들지 않음")
    return parser.parse_args()


def read_classes(folder: Path) -> list[str]:
    path = folder / "classes.txt"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def choose_class_id(classes: list[str], supplied: int | None) -> int:
    if classes:
        print("\n클래스 목록:")
        for index, name in enumerate(classes):
            print(f"  {index}: {name}")

    if supplied is not None:
        class_id = supplied
    else:
        coffee_ids = [i for i, name in enumerate(classes) if "coffee" in name.lower()]
        default = coffee_ids[0] if len(coffee_ids) == 1 else None
        prompt = f"추가할 클래스 ID [{default}]: " if default is not None else "추가할 클래스 ID: "
        answer = input(prompt).strip()
        if not answer and default is not None:
            class_id = default
        else:
            try:
                class_id = int(answer)
            except ValueError as exc:
                raise SystemExit("클래스 ID는 0 이상의 정수여야 합니다.") from exc

    if class_id < 0 or (classes and class_id >= len(classes)):
        raise SystemExit(f"유효하지 않은 클래스 ID입니다: {class_id}")
    return class_id


def choose_roi(image_path: Path) -> tuple[float, float, float, float]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise SystemExit(f"이미지를 열 수 없습니다: {image_path}")

    height, width = image.shape[:2]
    max_width, max_height = 1400, 850
    scale = min(1.0, max_width / width, max_height / height)
    shown = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1 else image.copy()

    title = "Draw coffee cup box - ENTER/SPACE: OK, C/ESC: Cancel"
    print("\n마우스로 커피컵을 드래그한 뒤 Enter 또는 Space를 누르세요.")
    x, y, box_width, box_height = cv2.selectROI(title, shown, showCrosshair=True)
    cv2.destroyAllWindows()
    if box_width <= 0 or box_height <= 0:
        raise SystemExit("박스 선택이 취소되었습니다. 라벨은 변경하지 않았습니다.")

    x, y, box_width, box_height = (value / scale for value in (x, y, box_width, box_height))
    x_center = (x + box_width / 2) / width
    y_center = (y + box_height / 2) / height
    return x_center, y_center, box_width / width, box_height / height


def append_labels(
    folder: Path,
    images: list[Path],
    label_line: str,
    make_backup: bool,
) -> tuple[int, int, Path | None]:
    targets = [(image, image.with_suffix(".txt")) for image in images]
    missing = [label for _, label in targets if not label.exists()]
    if missing:
        sample = "\n".join(f"  {path.name}" for path in missing[:10])
        raise SystemExit(f"대응하는 라벨 파일이 없는 이미지가 있습니다:\n{sample}")

    backup_dir = None
    if make_backup:
        backup_dir = folder / f"labels_backup_{datetime.now():%Y%m%d_%H%M%S}"
        backup_dir.mkdir()
        for _, label in targets:
            shutil.copy2(label, backup_dir / label.name)

    added = skipped = 0
    for _, label in targets:
        old_text = label.read_text(encoding="utf-8-sig")
        lines = [line.strip() for line in old_text.splitlines() if line.strip()]
        if label_line in lines:
            skipped += 1
            continue
        lines.append(label_line)
        label.write_text("\n".join(lines) + "\n", encoding="utf-8")
        added += 1
    return added, skipped, backup_dir


def main() -> None:
    args = parse_args()
    folder = args.folder.resolve()
    if not folder.is_dir():
        raise SystemExit(f"폴더가 없습니다: {folder}")

    images = sorted(path for path in folder.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS)
    if not images:
        raise SystemExit(f"이미지 파일이 없습니다: {folder}")

    image_path = args.image.resolve() if args.image else images[0]
    if image_path not in images:
        raise SystemExit("대표 이미지는 대상 폴더 안의 이미지여야 합니다.")

    class_id = choose_class_id(read_classes(folder), args.class_id)
    coordinates = choose_roi(image_path)
    label_line = f"{class_id} " + " ".join(f"{value:.6f}" for value in coordinates)

    print(f"\n대표 이미지: {image_path.name}")
    print(f"추가할 라벨: {label_line}")
    print(f"대상 라벨 수: {len(images)}")
    if not args.yes and input("모든 라벨에 추가할까요? [y/N]: ").strip().lower() not in {"y", "yes"}:
        raise SystemExit("취소했습니다. 라벨은 변경하지 않았습니다.")

    added, skipped, backup_dir = append_labels(folder, images, label_line, not args.no_backup)
    print(f"\n완료: {added}개 추가, {skipped}개 중복 건너뜀")
    if backup_dir:
        print(f"원본 백업: {backup_dir}")


if __name__ == "__main__":
    main()
