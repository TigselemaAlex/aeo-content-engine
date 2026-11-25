"""Run FFmpeg to extract the audio of a video and to cut the clip mezzanine.

Only running FFmpeg lives here: the arguments of the clip cut are built by the pure clip
domain (`ffmpeg_args.py`, docs/06 §5.2). Times are milliseconds of the source video. The
`ffmpeg` program must be on the PATH.
"""

import subprocess
from pathlib import Path

from content_engine.piece_types.clip.domain.ffmpeg_args import build_extract_args
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
