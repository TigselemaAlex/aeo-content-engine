"""Draw face boxes on frames of a video and save them as JPG images, to check them by eye.

Box positions are in pixels of the full-size video that is read (the mezzanine) and box
times in milliseconds from its start (docs/03 §5.3). Used by the `detect-faces` command
(docs/07 T2.1, step 5).
"""

from pathlib import Path

import cv2

from content_engine.piece_types.clip.domain.faces import FaceBox

BOX_COLOR = (0, 255, 0)  # green (Open Cv uses BGR)
"""Color of the drawn box: pure green, written (blue, green, red) because OpenCV uses BGR.

Picked by the developer so the box shows up clearly; it can be changed.
"""
BOX_THICKNESS = 4
"""Line width of the drawn box, in pixels of the full-size frame.

Picked by the developer so the box shows up clearly on a 1920x1080 frame; it can be changed.
"""


def save_face_preview(
    video_path: Path, boxes: list[FaceBox], output_dir: Path, count: int = 5
) -> list[Path]:
    """Draw a few face boxes on their full-size frames and save them as JPG images.

    Picks `count` boxes spread evenly over the list, so a person can check by eye that
    the box sits on the face. The picked positions are `i x len(boxes) // count` for
    i = 0 to count - 1, without repeats, so a list shorter than `count` gives fewer
    images. For each box it reads the frame `round(t_ms x fps / 1000)`, with the real
    frame rate of the video (ms -> frame), draws the box with BOX_COLOR and
    BOX_THICKNESS, and saves it as `face_<t_ms>.jpg`, with `t_ms` padded to six digits.
    A box partly out of frame is drawn up to the edge. A frame that cannot be read is
    skipped. An image with the same name is overwritten.

    Args:
        video_path: Video the boxes were detected on, normally the mezzanine.
        boxes: Face boxes in pixels of that video, for example the output of
            `pick_main_face`. Read in list order; they are spread over time if the list
            is sorted by `t_ms`.
        output_dir: Folder for the images. Created if missing.
        count: How many boxes to draw. 5 by default, picked by the developer as enough
            to check by eye; it can be changed.

    Returns:
        The paths of the saved images, in the order of the picked boxes. An empty list if
        `boxes` is empty; then the video is not opened and the folder is not created.

    Raises:
        RuntimeError: If the video cannot be opened or an image cannot be saved.

    Example:
        The main face of the test mezzanine (words 29 to 108, 30 fps) has 335 boxes, one
        every 100 ms. With count 5 the picked positions are 0 x 335 // 5 = 0, then 67,
        134, 201 and 268. The box at position 67 is at 6700 ms, drawn on frame
        round(6700 x 30 / 1000) = 201. The images are `face_000000.jpg`,
        `face_006700.jpg`, `face_013400.jpg`, `face_020100.jpg` and `face_026800.jpg`,
        each 1920x1080.
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
