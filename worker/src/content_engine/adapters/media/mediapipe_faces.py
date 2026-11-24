# pyright: basic

from collections.abc import Iterator
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceDetector, FaceDetectorOptions, RunningMode

from content_engine.piece_types.clip.domain.faces import FaceBox

Frame = np.typing.NDArray[np.uint8]


def _read_frames(
    video_path: Path, sample_fps: int = 10, target_width: int = 640
) -> Iterator[tuple[int, Frame, float]]:
    """Yield (t_ms, frame, scale) at sample_fps, downscaled to target_width.

    Frames are BGR, as OpenCV reads them. Multiply by scale to get back to
    original video pixels.
    """

    video = cv2.VideoCapture(str(video_path))

    if not video.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    try:
        fps = video.get(cv2.CAP_PROP_FPS)
        width = video.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = video.get(cv2.CAP_PROP_FRAME_HEIGHT)

        if fps <= 0 or width <= 0:
            raise RuntimeError(f"Could not read fps or size of video: {video_path}")

        step = max(1, round(fps / sample_fps))
        target_height = round(height * target_width / width)

        scale = width / target_width

        index = 0
        while video.grab():
            if index % step == 0:
                ok, frame = video.retrieve()
                if not ok:
                    break
                small = cv2.resize(
                    frame, (target_width, target_height), interpolation=cv2.INTER_AREA
                )

                t_ms = round(index * 1000 / fps)

                yield t_ms, np.asarray(small, dtype=np.uint8), scale
            index += 1
    finally:
        video.release()


def detect_faces(video_path: Path, model_path: Path) -> list[FaceBox]:
    """Detect every face in the video, sampled at 10 fps.

    Boxes are in original video pixels. A frame can have zero, one or
    several faces; picking the main one happens in the domain.
    """
    options = FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=str(model_path)), running_mode=RunningMode.VIDEO
    )

    faces: list[FaceBox] = []
    with FaceDetector.create_from_options(options) as detector:
        for t_ms, frame, scale in _read_frames(video_path=video_path):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = detector.detect_for_video(image, t_ms)

            for detection in result.detections:
                box = detection.bounding_box
                faces.append(
                    FaceBox(
                        t_ms=t_ms,
                        x=round(box.origin_x * scale),
                        y=round(box.origin_y * scale),
                        w=round(box.width * scale),
                        h=round(box.height * scale),
                        score=detection.categories[0].score,
                    )
                )
    return faces
