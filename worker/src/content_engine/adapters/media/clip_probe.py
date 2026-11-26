"""Measure a composed vertical clip for `verify-clip`: ffprobe data and frame matches.

Only the reading lives here (ffprobe and OpenCV); the limits are applied by the pure clip
domain (`verify.py`). Window positions and sizes are mezzanine pixels, as in
`CropKeyframe`, and frames are counted from 0 at 30 fps. The `ffprobe` program must be
on the PATH.
"""

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

from content_engine.piece_types.clip.domain.camera_path import CropKeyframe
from content_engine.piece_types.clip.domain.verify import (
    FrameMatch,
    VideoInfo,
    windows_to_compare,
)


def probe_video(path: Path) -> VideoInfo:
    """Read the size, frame rate, frame count and durations of a video with ffprobe.

    Runs ffprobe with `-count_frames`, which decodes the whole video stream to count
    its frames instead of trusting the header. The size, frame rate and frame count
    come from the first video stream; the audio duration from the first audio stream,
    if there is one. ffprobe's output is captured, not printed, and ffprobe is stopped
    after 300 s.

    Args:
        path: Video to read, for example the vertical clip from `compose_clip`.

    Returns:
        The video's measurements, durations in milliseconds.

    Raises:
        RuntimeError: If ffprobe exits with an error (the message carries its error
            output), if the file has no video stream, or if ffprobe's data is
            incomplete: a missing field, a value that is not a number, or a frame
            rate of "0/0".
        subprocess.TimeoutExpired: If ffprobe runs for more than 300 s.

    Example:
        The vertical clip of the test stretch (words 29 to 108) gives 1080x1920 at
        30 fps, 1004 frames, 33466.667 ms of video (1004 x 1000 / 30) and 33476 ms of
        audio.
    """
    args = [
        "ffprobe",
        "-v",
        "error",
        "-count_frames",
        "-show_entries",
        "stream=codec_type,width,height,r_frame_rate,nb_read_frames,duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(args, check=True, capture_output=True, timeout=300)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"ffprobe failed: {error.stderr.decode()}") from error

    try:
        streams = json.loads(result.stdout)["streams"]
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    except (KeyError, ValueError) as error:
        raise RuntimeError(f"ffprobe gave unreadable output for {path}: {error!r}") from error
    if video is None:
        raise RuntimeError(f"{path} has no video stream")
    try:
        num, den = (int(part) for part in video["r_frame_rate"].split("/"))
        return VideoInfo(
            width=int(video["width"]),
            height=int(video["height"]),
            fps=num / den,
            frames=int(video["nb_read_frames"]),
            video_duration_ms=float(video["duration"]) * 1000,
            audio_duration_ms=float(audio["duration"]) * 1000 if audio else None,
        )
    except (KeyError, ValueError, ZeroDivisionError) as error:
        raise RuntimeError(f"ffprobe gave incomplete data for {path}: {error!r}") from error


def _gray_frames(path: Path) -> Iterator[np.ndarray]:
    """Yield the frames of a video one by one, in order, converted to gray with OpenCV."""
    capture = cv2.VideoCapture(str(path))
    try:
        while True:
            ok, image = capture.read()
            if not ok:
                return
            yield cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    finally:
        capture.release()


def _match_db(output: np.ndarray, source: np.ndarray, window: CropKeyframe) -> float:
    """Return how well an output frame matches one window of a mezzanine frame, in dB.

    Crops `source` (a gray mezzanine frame) at `window`, shrinks `output` (a gray
    1080x1920 frame) back to the window size by averaging pixels (`INTER_AREA`) and
    compares the two with PSNR: the higher, the closer.
    """
    reference = source[window.y : window.y + window.h, window.x : window.x + window.w]
    shrunk = cv2.resize(output, (window.w, window.h), interpolation=cv2.INTER_AREA)
    return float(cv2.PSNR(shrunk, reference))


def match_frames(
    mezzanine_path: Path, clip_path: Path, keyframes: list[CropKeyframe]
) -> list[FrameMatch]:
    """Compare every frame of the clip with its own crop window and its neighbours'.

    Reads the mezzanine and the clip frame by frame, side by side. Each clip frame is
    matched (`_match_db`) against the mezzanine frame cropped at its own keyframe, and
    at the neighbour windows that `windows_to_compare` picks (previous and next frame,
    only when their window differs from its own); the best neighbour is kept. A frame
    that shows its window one frame early or late then matches a neighbour better than
    its own, which `FrameMatch.neighbour_wins` detects. It stops at the shortest of the two videos
    and the keyframes, so a clip with missing frames gives fewer matches.

    Args:
        mezzanine_path: Mezzanine the clip was made from.
        clip_path: Vertical clip from `compose_clip`.
        keyframes: The camera path the clip was made with, one keyframe per frame.

    Returns:
        One match per compared frame, in frame order.

    Example:
        On the test stretch (words 29 to 108) it gives 1004 matches; the worst own
        match is 43.9 dB. On the cut frame 96 the frame matches its own 552x982
        bridge window at 49.4 dB and the 608x1080 window of frame 95 at 16.3 dB.
        355 frames have no neighbour with a different window (`neighbour_db` None).
    """
    matches: list[FrameMatch] = []
    pairs = zip(_gray_frames(mezzanine_path), _gray_frames(clip_path), keyframes, strict=False)
    for frame, (source, output, window) in enumerate(pairs):
        own = _match_db(output, source, window)
        neighbours = [
            _match_db(output, source, other) for other in windows_to_compare(keyframes, frame)
        ]
        matches.append(
            FrameMatch(frame=frame, own_db=own, neighbour_db=max(neighbours, default=None))
        )
    return matches
