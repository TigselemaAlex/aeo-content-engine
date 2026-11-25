# pyright: basic

"""Detect faces in a video with MediaPipe Face Detector.

Frames are read with OpenCV, sampled at 10 fps and shrunk to 640 px wide before detection
(docs/03 §5.3). Boxes are scaled back to pixels of the full-size video, and times are
milliseconds from its start. This is the only file that imports MediaPipe, which ships no
types, so it is checked with `pyright: basic` instead of `strict` (docs/00 "Tipos en
Python").
"""

from collections.abc import Iterator
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceDetector, FaceDetectorOptions, RunningMode

from content_engine.piece_types.clip.domain.faces import FaceBox

Frame = np.typing.NDArray[np.uint8]
"""A frame as OpenCV reads it: a height x width x 3 array of 8-bit values, in BGR order."""


def _read_frames(
    video_path: Path, sample_fps: int = 10, target_width: int = 640
) -> Iterator[tuple[int, Frame, float]]:
    """Yield `(t_ms, frame, scale)` for the sampled frames, shrunk to `target_width`.

    Keeps one frame every `max(1, round(fps / sample_fps))` frames of the video and
    resizes it to `target_width` wide, keeping the aspect ratio. The defaults, 10 fps
    and 640 px, come from docs/03 §5.3. With a frame rate that is not a multiple of
    `sample_fps` the rate is only close: 24 fps keeps every round(24 / 10) = 2nd frame,
    12 per second. Frames are BGR, as OpenCV reads them.

    Yields:
        `t_ms`: `round(frame index x 1000 / fps)`, milliseconds from the start of the
        video (frame -> ms). `frame`: the shrunk frame. `scale`: video width /
        `target_width`; multiply a position in the shrunk frame by it to get pixels of
        the full-size video.

    Raises:
        RuntimeError: If the video cannot be opened, or its frame rate or width reads
            as 0.

    Example:
        On the 1920x1080 mezzanine at 30 fps: step = round(30 / 10) = 3, so frames 0, 3,
        6... are kept, at t_ms 0, 100, 200... Each is resized to 640 x
        round(1080 x 640 / 1920) = 640x360, and scale = 1920 / 640 = 3.0.
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
    """Detect every face in a video and return the boxes in full-size video pixels.

    Runs MediaPipe Face Detector in video mode on the frames from `_read_frames` (10 fps,
    640 px wide, docs/03 §5.3) and multiplies each box by `scale`, rounded to whole
    pixels, to go back to pixels of the full-size video. Boxes are not clipped to the
    frame: when a face is partly out of frame, x or y can be negative (seen on the test
    recording). A frame can have zero, one or several faces; picking the main one is a
    rule of the clip domain (`pick_main_face`). `score` is the confidence of the
    detection's first category.

    Args:
        video_path: Video to analyze, normally the mezzanine.
        model_path: MediaPipe face detection model. The worker uses
            `models/blaze_face_short_range.tflite` (docs/00 "Modelo de detección de
            caras").

    Returns:
        Every box found, in time order, with `t_ms` in milliseconds from the start of the
        video. An empty list if no face was found.

    Raises:
        RuntimeError: If the video cannot be opened, or its frame rate or width reads
            as 0.

    Example:
        The 1920x1080 test mezzanine (words 29 to 108: 1004 frames, 33.5 s at 30 fps) is
        read as 335 frames of 640x360 (one every 3, so one every 100 ms), with scale
        1920 / 640 = 3.0, and gives 335 boxes, one per frame. The first box is at
        (283, 75), 183x183, in the small frame; in the mezzanine that is
        (283 x 3.0, 75 x 3.0) = (849, 225), 549x549.
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
