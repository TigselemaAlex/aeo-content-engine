import subprocess
from pathlib import Path

from content_engine.piece_types.clip.domain.ffmpeg_args import build_extract_args
from content_engine.piece_types.clip.domain.timeline import Timeline


def extract_audio(video_path: Path, audio_path: Path) -> None:
    """Extract a mono 16kHz ACC audio track from video."""

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
    """Extract a clip from timeline"""

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
