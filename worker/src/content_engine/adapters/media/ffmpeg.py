"""Run FFmpeg to extract the audio of a video, cut the clip mezzanine and compose the clip.

Only running FFmpeg lives here: the arguments of the clip cut and of the compose, and
the crop commands, are built by the pure clip domain (`ffmpeg_args.py` and `sendcmd.py`,
docs/06 §5.2). Cut times are milliseconds of the source video; crop windows are pixels
and frames of the mezzanine. The `ffmpeg` program must be on the PATH.
"""

import functools
import subprocess
import tempfile
from pathlib import Path

from content_engine.piece_types.clip.domain.camera_path import CropKeyframe
from content_engine.piece_types.clip.domain.ffmpeg_args import (
    MIN_FFMPEG_MAJOR,
    build_compose_args,
    build_extract_args,
    ffmpeg_supports_variable_crop,
)
from content_engine.piece_types.clip.domain.sendcmd import crop_commands
from content_engine.piece_types.clip.domain.timeline import Timeline


def extract_audio(video_path: Path, audio_path: Path) -> None:
    """Extract the audio track of a video as a mono 16 kHz AAC file, for transcription.

    Runs FFmpeg without the image (`-vn`), mixed down to one channel at 16,000 samples
    per second and encoded as AAC at 64 kbps: a light file to send to AssemblyAI (mono
    16 kHz: docs/01 §4.2 step 3 and docs/04 §4.1 `extract_audio`). 64 kbps was picked by
    the developer for acceptable quality in a light file that uploads fast; it did not
    come from a comparison test (decision "Audio para transcribir", docs/00). The
    container follows the extension of `audio_path`; the pipeline uses `.m4a`
    (docs/01 §4.2). An existing file at `audio_path` is overwritten (`-y`). FFmpeg's
    output is captured, not printed, and FFmpeg is stopped after 600 s, on purpose the
    same 10 min limit the step catalog gives `extract_audio` (docs/04 §4.1).

    Args:
        video_path: Video to read the audio from, for example the original upload.
        audio_path: Where to write the audio file. Its folder must already exist.

    Raises:
        RuntimeError: If FFmpeg exits with an error. The message carries FFmpeg's error
            output.
        subprocess.TimeoutExpired: If FFmpeg runs for more than 600 s.

    Example:
        The 3 min 18 s test recording (1920x1080 at 24 fps, stereo AAC at 48 kHz, 490 MB)
        gives a 1.6 MB `.m4a`: AAC, 1 channel, 16000 Hz, about 64 kbps.
    """
    args = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        str(audio_path),
    ]
    try:
        subprocess.run(args, check=True, capture_output=True, timeout=600)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"FFmpeg failed: {error.stderr.decode()}") from error


def extract_clip(video_path: Path, timeline: Timeline, output_path: Path, fps: int = 30) -> None:
    """Cut the timeline's ranges out of a video and join them into the clip mezzanine.

    The FFmpeg arguments come from `build_extract_args`, a pure function of the clip
    domain; this adapter only runs FFmpeg (docs/03 §5.2). Each range is read straight
    from its place in the source (input seeking). The video ranges (`Timeline.video_cuts`)
    and the audio ranges (`Timeline.cuts`) are joined as two separate tracks, so the
    J cuts keep their offset. The result is H.264 (CRF 16, preset `veryfast`, `yuv420p`)
    at a constant `fps`, with AAC audio at 48 kHz and 192 kbps (docs/03 §5.2). An
    existing file at `output_path` is overwritten. FFmpeg's output is captured, not
    printed, and FFmpeg is stopped after 600 s, the same 10 min the step catalog gives
    `clip.extract` (docs/04 §4.1).

    Args:
        video_path: Source video, usually the original upload. The timeline's times are
            milliseconds of this video.
        timeline: Audio and video ranges to keep, from `build_timeline`.
        output_path: Where to write the mezzanine, for example `mezzanine.mp4`. Its folder
            must already exist.
        fps: Frame rate of the mezzanine. 30 by default: the constant rate that every
            later step counts frames with (docs/03 §5.2).

    Raises:
        ValueError: If a video range is too short to get a whole frame at `fps`. Raised
            by `build_extract_args`, before FFmpeg runs.
        RuntimeError: If FFmpeg exits with an error. The message carries FFmpeg's error
            output.
        subprocess.TimeoutExpired: If FFmpeg runs for more than 600 s.

    Example:
        On the test recording (1920x1080 at 24 fps), words 29 to 108 give a timeline of
        10 cuts and 33476 ms. The mezzanine comes out 1920x1080 at 30 fps, with
        round(33476 x 30 / 1000) = round(1004.28) = 1004 frames.
    """
    args = [
        "ffmpeg",
        *build_extract_args(
            source=str(video_path), timeline=timeline, output=str(output_path), fps=fps
        ),
    ]

    try:
        subprocess.run(args, check=True, capture_output=True, timeout=600)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"FFmpeg failed: {error.stderr.decode()}") from error


@functools.cache
def _ffmpeg_version() -> str:
    """Return what `ffmpeg -version` prints, run once per process and cached.

    The 30 s limit is only a safety cap, picked by the developer without measuring: the
    command answers at once.

    Raises:
        RuntimeError: If `ffmpeg -version` exits with an error. The message carries its
            error output.
        subprocess.TimeoutExpired: If it takes more than 30 s.
    """
    try:
        result = subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, timeout=30)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"ffmpeg -version failed: {error.stderr.decode()}") from error
    return result.stdout.decode(errors="replace")


def compose_clip(mezzanine_path: Path, keyframes: list[CropKeyframe], output_path: Path) -> None:
    """Crop the mezzanine along the camera path and scale it to the 1080x1920 vertical clip.

    Before the compose it checks the FFmpeg on the PATH with
    `ffmpeg_supports_variable_crop`: an FFmpeg older than `MIN_FFMPEG_MAJOR` (9) crashes
    or hangs when the crop window changes size (docs/03 §5.6), so the compose stops with
    a clear error instead of hanging until its time limit. `ffmpeg -version` runs only
    once per process.

    Then it writes the `crop_commands` script to `crop.cmd` in a temporary folder and
    runs FFmpeg with `build_compose_args` from that folder, so the filter receives the
    bare file name: a Windows path such as `C:/...` inside a filter argument breaks on
    the `:`.
    The clip is H.264 High in yuv420p at 30 fps with `+faststart`, and the mezzanine's
    audio is copied as it is (docs/03 §5.6). There is no frame rate argument: the
    command times of `crop_commands` follow the 30 fps of the mezzanine (docs/03 §5.2)
    and the clip's own rate is 30 fps by design (docs/03 §5.6), so both use their
    default of 30. The temporary folder is deleted at the end. An existing file at
    `output_path` is overwritten. FFmpeg's output is captured, not printed, and FFmpeg
    is stopped after 900 s, the same 15 min the step catalog gives `clip.compose`
    (docs/04 §4.1).

    Args:
        mezzanine_path: Mezzanine from `extract_clip`.
        keyframes: One crop window per mezzanine frame, in frame order, from
            `camera_path`.
        output_path: Where to write the clip, for example `clip.mp4`. Its folder must
            already exist.

    Raises:
        ValueError: If `keyframes` is empty, before FFmpeg runs.
        RuntimeError: If the FFmpeg on the PATH is older than 9, before the compose
            runs; the message carries the first line of `ffmpeg -version`. Also if
            `ffmpeg -version` or the compose exits with an error; the message then
            carries FFmpeg's error output.
        subprocess.TimeoutExpired: If FFmpeg runs for more than 900 s, or
            `ffmpeg -version` takes more than 30 s (a safety cap, not measured).

    Example:
        On the test stretch (words 29 to 108) the 1004 keyframes give a 579-line
        `crop.cmd`, and the clip comes out 1080x1920 at 30 fps with 1004 frames, in
        about 7 s. With Ubuntu 24.04's FFmpeg 6.1.1 it stops at once with
        `RuntimeError: compose needs FFmpeg 9 or later, found: ffmpeg version
        6.1.1-3ubuntu5 Copyright (c) 2000-2023 the FFmpeg developers. Older versions
        crash or hang when the crop changes size (docs/03 section 5.6).`
    """
    if not keyframes:
        raise ValueError("the camera path has no keyframes")
    version = _ffmpeg_version()
    if not ffmpeg_supports_variable_crop(version):
        raise RuntimeError(
            f"compose needs FFmpeg {MIN_FFMPEG_MAJOR} or later, found: {version.splitlines()[0]}. "
            "Older versions crash or hang when the crop changes size (docs/03 section 5.6)."
        )
    with tempfile.TemporaryDirectory() as work_dir:
        commands_file = Path(work_dir) / "crop.cmd"
        commands_file.write_text(crop_commands(keyframes), encoding="utf8")
        args = [
            "ffmpeg",
            *build_compose_args(
                mezzanine=str(mezzanine_path.resolve()),
                first=keyframes[0],
                commands_file=commands_file.name,
                output=str(output_path.resolve()),
            ),
        ]
        try:
            subprocess.run(args, check=True, capture_output=True, timeout=900, cwd=work_dir)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"FFmpeg failed: {error.stderr.decode()}") from error
