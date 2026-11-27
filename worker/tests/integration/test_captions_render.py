"""Burn captions into a real vertical clip and check them on the frames FFmpeg wrote.

Guards what the unit tests cannot see: that libass draws each word on the frame the ASS
file says (the compose keeps the mezzanine's clock), that it uses Figtree from
`assets/fonts` and stops when the font is missing instead of falling back, and that the
orange comes out as #FF7B2A when a player decodes the BT.709 clip (without the
`YCbCr Matrix: TV.709` line it came out as #FF8124, measured on 26 nov 2026). It renders
a flat gray synthetic mezzanine, so any dark or white pixel is a caption. Skipped when
`ffmpeg` or `ffprobe` is not on the PATH, except in CI, as `test_compose_render.py`.
"""

import os
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from content_engine.adapters.media.ffmpeg import compose_clip
from content_engine.adapters.media.libass import probe_captions
from content_engine.piece_types.clip.domain.camera_path import CropKeyframe
from content_engine.piece_types.clip.domain.caption_checks import check_captions, highlight_plane
from content_engine.piece_types.clip.domain.captions_ass import (
    CaptionStyle,
    ClipWord,
    captions_ass,
    plan_captions,
)
from content_engine.piece_types.clip.domain.faces import FaceBox
from content_engine.piece_types.clip.domain.timeline import Cut, Timeline
from content_engine.shared.transcript import Word

FFMPEG_MISSING = shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None

pytestmark = pytest.mark.skipif(
    FFMPEG_MISSING and not os.environ.get("CI"),
    reason="needs ffmpeg and ffprobe on the PATH (required in CI)",
)

FONTS = Path(__file__).resolve().parents[2] / "assets" / "fonts"
STYLE = CaptionStyle()
FRAMES = 60
KEYFRAMES = [
    CropKeyframe(t_ms=round(f * 1000 / 30), x=656, y=0, w=608, h=1080) for f in range(FRAMES)
]
FACES = [FaceBox(t_ms=0, x=700, y=300, w=500, h=500, score=0.9)]
# "Hello" turns white on frame 15 (500 ms) and "world." on frame 30 (1000 ms).
WORDS = [
    ClipWord(i=0, text="Hello", start_ms=500, end_ms=900, cut=0),
    ClipWord(i=1, text="world.", start_ms=1000, end_ms=1600, cut=0),
]


def gray_mezzanine(path: Path) -> None:
    # 2 s of flat gray at 1920x1080 and 30 fps with a tone, tagged BT.709 like the
    # recordings, so every dark or white pixel of the clip belongs to the captions.
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=gray:size=1920x1080:rate=30:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2:sample_rate=48000",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )


def write_captions(path: Path, style: CaptionStyle = STYLE) -> None:
    plan = plan_captions(WORDS, KEYFRAMES, FACES, cut_frame_ms=[], style=style)
    path.write_text(captions_ass(plan, style), encoding="utf8")


def gray_frames(path: Path) -> list[np.ndarray]:
    capture = cv2.VideoCapture(str(path))
    frames: list[np.ndarray] = []
    while True:
        ok, image = capture.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    capture.release()
    return frames


def white_center_x(frame: np.ndarray) -> float | None:
    columns = np.nonzero(frame > 230)[1]
    return float(columns.mean()) if columns.size else None


def test_captions_are_burned_on_their_frames(tmp_path: Path) -> None:
    mezzanine, captions, clip = (
        tmp_path / "mezzanine.mp4",
        tmp_path / "captions.ass",
        tmp_path / "clip.mp4",
    )
    gray_mezzanine(mezzanine)
    write_captions(captions)

    compose_clip(mezzanine, KEYFRAMES, clip, captions_path=captions, fonts_dir=FONTS)

    frames = gray_frames(clip)
    assert len(frames) == FRAMES
    dark = [int((frame < 40).sum()) for frame in frames]
    assert dark[14] == 0 and dark[15] > 10_000
    # The highlight moves from "Hello" to "world." between frames 29 and 30, and stays.
    before, at, after = (white_center_x(frames[k]) for k in (29, 30, 31))
    assert before is not None and at is not None and after is not None
    assert at - before > 100
    assert abs(after - at) < 3


def test_the_orange_survives_the_bt709_clip(tmp_path: Path) -> None:
    mezzanine, captions, clip = (
        tmp_path / "mezzanine.mp4",
        tmp_path / "captions.ass",
        tmp_path / "clip.mp4",
    )
    gray_mezzanine(mezzanine)
    write_captions(captions)
    compose_clip(mezzanine, KEYFRAMES, clip, captions_path=captions, fonts_dir=FONTS)

    rgb = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(clip),
            "-vf",
            "select=eq(n\\,45),scale=in_color_matrix=bt709:in_range=tv:out_range=pc,format=rgb24",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-",
        ],
        check=True,
        capture_output=True,
        timeout=60,
    ).stdout
    pixels = np.frombuffer(rgb, dtype=np.uint8).reshape(-1, 3).astype(int)
    orange = pixels[(pixels[:, 0] > 200) & (pixels[:, 2] < 120) & (abs(pixels[:, 1] - 123) < 40)]
    values, counts = np.unique(orange, axis=0, return_counts=True)
    most_common = values[np.argmax(counts)]

    assert np.abs(most_common - np.array([255, 123, 42])).max() <= 4


def test_measured_captions_pass_the_checks(tmp_path: Path) -> None:
    captions = tmp_path / "captions.ass"
    write_captions(captions)

    frames, fonts = probe_captions(captions, FONTS, FRAMES, highlight=highlight_plane(STYLE))
    checks = check_captions(
        ass_text=captions.read_text(encoding="utf8"),
        words=[
            Word(
                i=w.i,
                text=w.text,
                start_ms=w.start_ms,
                end_ms=w.end_ms,
                speaker="A",
                confidence=1.0,
                is_disfluency=False,
            )
            for w in WORDS
        ],
        timeline=Timeline(
            cuts=[Cut(start_ms=0, end_ms=2000)], video_cuts=[Cut(start_ms=0, end_ms=2000)]
        ),
        frames=frames,
        fonts=fonts,
        keyframes=KEYFRAMES,
        faces=FACES,
        cut_frames=[],
    )

    results = {check.name: check for check in checks}
    assert results["caption font"].ok, results["caption font"].value
    assert results["caption words"].ok
    assert results["caption sync"].ok, results["caption sync"].value
    assert results["captions clear of face"].ok


def test_compose_stops_when_libass_would_use_another_font(tmp_path: Path) -> None:
    mezzanine, captions, clip = (
        tmp_path / "mezzanine.mp4",
        tmp_path / "captions.ass",
        tmp_path / "clip.mp4",
    )
    gray_mezzanine(mezzanine)
    write_captions(captions, CaptionStyle(font_name="Figtreee"))

    with pytest.raises(RuntimeError, match="libass picked: Figtreee"):
        compose_clip(mezzanine, KEYFRAMES, clip, captions_path=captions, fonts_dir=FONTS)
    assert not clip.exists()


def test_compose_stops_without_font_files(tmp_path: Path) -> None:
    mezzanine, captions, clip = (
        tmp_path / "mezzanine.mp4",
        tmp_path / "captions.ass",
        tmp_path / "clip.mp4",
    )
    gray_mezzanine(mezzanine)
    write_captions(captions)
    empty = tmp_path / "no-fonts"
    empty.mkdir()

    with pytest.raises(RuntimeError, match="no font files"):
        compose_clip(mezzanine, KEYFRAMES, clip, captions_path=captions, fonts_dir=empty)
