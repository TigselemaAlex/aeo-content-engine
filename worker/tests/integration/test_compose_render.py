"""Render a real vertical clip with FFmpeg and check that every frame shows its own window.

Guards the two render details the unit tests cannot see: `exact=1` on the crop and the
half-frame timing of the `sendcmd` commands. It renders a synthetic 2 s mezzanine
(FFmpeg's `testsrc2` at 1920x1080 and 30 fps, no recording needed) along a path that
moves 1 px per frame from an odd x and switches to a 552x982 bridge on frame 30, and
checks with `match_frames` that no frame matches a neighbour's window better than its
own. Measured on 26 nov 2026: without `exact=1`, frames 2, 4, 6... fail (crop rounds odd
x down to even); with the commands timed at each keyframe's `t_ms`, frames 2, 5, 8...
fail (one frame late every third frame). Skipped when `ffmpeg` or `ffprobe` is not on
the PATH.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from content_engine.adapters.media.clip_probe import match_frames, probe_video
from content_engine.adapters.media.ffmpeg import compose_clip
from content_engine.piece_types.clip.domain.camera_path import CropKeyframe

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="needs ffmpeg and ffprobe on the PATH",
)


def synthetic_mezzanine(path: Path) -> None:
    # 2 s of FFmpeg's sharp test pattern at 1920x1080 and 30 fps, with a tone: no
    # recording needed, and its hard edges tell a 1 px shift apart.
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1920x1080:rate=30:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2:sample_rate=48000",
            "-c:v",
            "libx264",
            "-crf",
            "12",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )


def path_with_a_bridge() -> list[CropKeyframe]:
    # 1 px per frame from x 601 (odd x included, which crop needs exact=1 for), then a
    # 552x982 cut bridge on frame 30 that keeps moving: sizes change mid-video.
    keyframes: list[CropKeyframe] = []
    for frame in range(60):
        t_ms = round(frame * 1000 / 30)
        if frame < 30:
            keyframes.append(CropKeyframe(t_ms=t_ms, x=601 + frame, y=0, w=608, h=1080))
        else:
            keyframes.append(CropKeyframe(t_ms=t_ms, x=700 + frame, y=49, w=552, h=982))
    return keyframes


def test_every_frame_shows_its_own_window(tmp_path: Path) -> None:
    mezzanine = tmp_path / "mezzanine.mp4"
    clip = tmp_path / "clip.mp4"
    synthetic_mezzanine(mezzanine)
    keyframes = path_with_a_bridge()

    compose_clip(mezzanine_path=mezzanine, keyframes=keyframes, output_path=clip)

    info = probe_video(clip)
    assert (info.width, info.height, info.fps, info.frames) == (1080, 1920, 30, 60)
    matches = match_frames(mezzanine, clip, keyframes)
    assert len(matches) == 60
    assert [m.frame for m in matches if m.neighbour_wins] == []
    assert min(m.own_db for m in matches) >= 35
