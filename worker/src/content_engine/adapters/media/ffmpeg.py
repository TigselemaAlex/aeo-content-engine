import subprocess
from pathlib import Path


def extract_audio(video_path: Path, audio_path: Path) -> None:
    """Extract a mono 16kHz ACC auido track from video."""

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
        raise RuntimeError(f"... {error.stderr.decode()}") from error
