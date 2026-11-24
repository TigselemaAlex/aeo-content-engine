from pathlib import Path

import cv2

from content_engine.piece_types.clip.domain.faces import FaceBox

BOX_COLOR = (0, 255, 0)  # green (Open Cv uses BGR)
BOX_THICKNESS = 4


def save_face_preview(
    video_path: Path, boxes: list[FaceBox], output_dir: Path, count: int = 5
) -> list[Path]:
    """Draw some face boxes on full-size frames and save them as JPG images.

    Picks `count` boxes spread evenly over the clip, so a person can check
    by eye that the box sits on the face.
    """
    if not boxes:
        return []

    chosen = list(dict.fromkeys(boxes[i * len(boxes) // count] for i in range(count)))

    video = cv2.VideoCapture(str(video_path))

    if not video.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    try:
        fps = video.get(cv2.CAP_PROP_FPS)
        for box in chosen:
            frame_index = round(box.t_ms * fps / 1000)
            video.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = video.read()
            if not ok:
                continue

            top_left = (box.x, box.y)
            bottom_right = (box.x + box.w, box.y + box.h)
            cv2.rectangle(frame, top_left, bottom_right, BOX_COLOR, BOX_THICKNESS)

            path = output_dir / f"face_{box.t_ms:06d}.jpg"
            if not cv2.imwrite(str(path), frame):
                raise RuntimeError(f"Could not save preview image: {path}")
            saved.append(path)
    finally:
        video.release()
    return saved
