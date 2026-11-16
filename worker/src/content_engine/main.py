from pathlib import Path

import typer
from pydantic import ValidationError

from content_engine.adapters.media.ffmpeg import extract_audio
from content_engine.config import Settings, get_settings

app = typer.Typer()


@app.callback()
def main() -> None:
    """Content Engine worker"""


def load_settings() -> Settings:
    try:
        return get_settings()
    except ValidationError as error:
        for item in error.errors():
            typer.echo(f"Missing or empty setting: {str(item['loc'][0]).upper()}", err=True)
        raise typer.Exit(code=1) from None


@app.command()
def hello() -> None:
    settings = load_settings()
    print(settings.claude_model_generate)


@app.command("extract-audio")
def extract_audio_command(video: Path, output: Path) -> None:
    """Exctract the audio track of a video for transcript."""
    extract_audio(video_path=video, audio_path=output)
    size_mb = output.stat().st_size / 1_000_000
    print(f"Audio saved to {output} ({size_mb:.1f} MB)")
