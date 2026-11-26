"""Command line of the worker, built with Typer.

Holds the development commands of the prototype: each one runs one step of the clip
pipeline on local files. Run them from `worker/` with
`uv run python -m content_engine <command>`; `<command> --help` shows the help of each one.
"""

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from content_engine.adapters.media.clip_probe import match_frames, probe_video
from content_engine.adapters.media.face_preview import save_face_preview
from content_engine.adapters.media.ffmpeg import compose_clip, extract_audio, extract_clip
from content_engine.adapters.media.mediapipe_faces import detect_faces
from content_engine.adapters.transcription.assemblyai import transcribe
from content_engine.config import Settings, get_settings
from content_engine.piece_types.clip.domain.camera_path import (
    CameraPath,
    camera_path,
    cut_at_frames,
)
from content_engine.piece_types.clip.domain.faces import FaceBox, pick_main_face
from content_engine.piece_types.clip.domain.ffmpeg_args import OUTPUT_H, OUTPUT_W
from content_engine.piece_types.clip.domain.path_checks import check_path
from content_engine.piece_types.clip.domain.timeline import (
    Segment,
    build_timeline,
    words_to_clip_ms,
)
from content_engine.piece_types.clip.domain.verify import verify_clip
from content_engine.shared.transcript import Transcript

app = typer.Typer()
"""The Typer app with every command; `python -m content_engine` and `content-engine` run it."""


@app.callback()
def main() -> None:
    """Content Engine worker.

    Development commands that run one step of the clip pipeline on local
    files: extract the audio, transcribe it, cut the mezzanine, find the
    face, build the camera path, compose the vertical clip and verify it.
    """


def load_settings() -> Settings:
    """Load the worker settings, or stop the command with a readable message.

    Reads the settings from the environment and the `.env` files (`get_settings`). If
    some are missing or empty, prints `Missing or empty setting: <NAME>` to stderr for
    each one, with the name of its environment variable, and exits with code 1 instead
    of showing Pydantic's traceback.

    Returns:
        The settings. `get_settings` caches them after the first call.

    Raises:
        typer.Exit: With code 1 if a setting is missing or empty.

    Example:
        With `ANTHROPIC_API_KEY` set to an empty string, it prints
        `Missing or empty setting: ANTHROPIC_API_KEY` and the command exits with code 1.
    """
    try:
        return get_settings()
    except ValidationError as error:
        for item in error.errors():
            typer.echo(f"Missing or empty setting: {str(item['loc'][0]).upper()}", err=True)
        raise typer.Exit(code=1) from None


@app.command()
def hello() -> None:
    """Print the Claude model that generates pieces, to check the settings.

    Reads the settings from the environment and the .env files and prints
    CLAUDE_MODEL_GENERATE. If ANTHROPIC_API_KEY or ASSEMBLYAI_API_KEY is
    missing or empty, it says which one and exits with code 1.
    """
    settings = load_settings()
    print(settings.claude_model_generate)


@app.command("extract-audio")
def extract_audio_command(
    video: Annotated[Path, typer.Argument(help="Video to take the audio from")],
    output: Annotated[Path, typer.Argument(help="Audio file to write (.m4a)")],
) -> None:
    """Extract the audio track of a video, for transcription.

    Writes the audio of VIDEO to OUTPUT as mono 16 kHz AAC, a light file
    to send to AssemblyAI (the container follows the extension of OUTPUT).
    Prints the size of the file in MB (1 MB = 1,000,000 bytes).
    """
    extract_audio(video_path=video, audio_path=output)
    size_mb = output.stat().st_size / 1_000_000
    print(f"Audio saved to {output} ({size_mb:.1f} MB)")


@app.command("transcribe")
def transcribe_audio_command(
    audio: Annotated[Path, typer.Argument(help="Audio file from extract-audio")],
    output: Annotated[Path, typer.Argument(help="Transcript JSON to write")],
) -> None:
    """Transcribe an audio file with AssemblyAI and save the transcript as JSON.

    Sends AUDIO with fillers kept ("um", "uh"), speaker labels and the
    glossary AEO, ChatGPT, and writes to OUTPUT every word with its index,
    text, times in milliseconds, speaker, confidence and whether it is a
    filler. Prints the number of words, the length in seconds and the
    number of fillers. Needs ASSEMBLYAI_API_KEY, and also ANTHROPIC_API_KEY
    because every command that loads the settings checks both.
    """
    settings = load_settings()
    transcript = transcribe(
        audio_path=audio,
        api_key=settings.assemblyai_api_key.get_secret_value(),
        glossary=["AEO", "ChatGPT"],
    )
    transcript_to_json = transcript.model_dump_json(indent=2)
    output.write_text(transcript_to_json, encoding="utf-8")
    fillers_count = sum(1 for w in transcript.words if w.is_disfluency)
    print(
        f"Transcript saved to {output} "
        f"({len(transcript.words)} words - "
        f"{transcript.duration_ms / 1000:.1f}s - {fillers_count} fillers)"
    )


@app.command("cut")
def cut_command(
    video: Annotated[Path, typer.Argument(help="Original video")],
    transcript_path: Annotated[Path, typer.Argument(help="Transcript JSON from transcribe")],
    from_word: Annotated[int, typer.Option("--from", help="First word index")],
    to_word: Annotated[int, typer.Option("--to", help="Last word index")],
    output: Annotated[Path, typer.Option(help="Output video")] = Path("mezzanine.mp4"),
) -> None:
    """Cut a word range out of the video, without fillers or long pauses.

    Keeps the words of the transcript from --from to --to (both included),
    drops the fillers, splits at pauses longer than 500 ms, adds J cuts and
    writes the mezzanine: the source resolution at 30 fps, H.264 with AAC
    audio. Prints the number of cuts and the length of the clip in
    milliseconds.
    """
    transcript = Transcript.model_validate_json(transcript_path.read_text(encoding="utf8"))
    timeline = build_timeline(
        words=transcript.words, segment=Segment(from_word=from_word, to_word=to_word)
    )

    extract_clip(video_path=video, timeline=timeline, output_path=output)

    print(
        f"Clip saved to {output} with {len(timeline.cuts)} cuts and {timeline.duration_ms:.1f}ms "
    )


@app.command("detect-faces")
def detect_faces_command(
    video: Annotated[Path, typer.Argument(help="Mezzanine from cut")],
    output: Annotated[Path, typer.Option(help="Output JSON")] = Path("faces.json"),
    previews: Annotated[Path, typer.Option(help="Folder for preview images")] = Path(
        "face-previews"
    ),
    model: Annotated[Path, typer.Option(help="Face detection model")] = Path(
        "models/blaze_face_short_range.tflite"
    ),
) -> None:
    """Find the main face over time; save it as JSON plus preview images.

    Detects faces in VIDEO 10 times per second, keeps the biggest and most
    persistent face, and saves its boxes in pixels of the video, with times
    in milliseconds from its start. Also draws 5 of the boxes on their
    frames as JPG images, to check them by eye. Run it from worker/ so the
    default --model path is found. Prints how many boxes the main face kept
    out of all the boxes found.
    """
    boxes = detect_faces(video_path=video, model_path=model)
    main_face = pick_main_face(boxes=boxes)

    data = [box.model_dump() for box in main_face]

    output.write_text(json.dumps(data, indent=2), encoding="utf8")

    images = save_face_preview(video_path=video, boxes=main_face, output_dir=previews)

    print(
        f"Main face saved to {output} "
        f"({len(main_face)} of {len(boxes)} boxes - {len(images)} previews in {previews})"
    )


@app.command("camera-path")
def camera_path_command(
    faces_path: Annotated[Path, typer.Argument(help="Faces JSON from detect-faces")],
    transcript_path: Annotated[Path, typer.Argument(help="Transcript JSON used with cut")],
    from_word: Annotated[int, typer.Option("--from", help="First word index")],
    to_word: Annotated[int, typer.Option("--to", help="Last word index")],
    frame_width: Annotated[int, typer.Option(help="Mezzanine width in pixels")],
    frame_height: Annotated[int, typer.Option(help="Mezzanine height in pixels")],
    zoom_words: Annotated[
        list[int] | None, typer.Option("--zoom-word", help="Word index to zoom on (repeatable)")
    ] = None,
    output: Annotated[Path, typer.Option(help="Output JSON")] = Path("camera-path.json"),
) -> None:
    """Build the crop keyframes that follow the face, with zooms and cut bridges.

    Rebuilds the cuts from the transcript, --from and --to, which must be
    the same ones given to cut so the cut points match the mezzanine.
    Writes one 9:16 crop window per frame at 30 fps (time in milliseconds,
    then x, y, width and height in mezzanine pixels) and the stretches
    without a face. Prints the number of keyframes, cut bridges, zooms and
    stretches without a face.
    """
    faces = TypeAdapter(list[FaceBox]).validate_json(faces_path.read_text(encoding="utf8"))
    transcript = Transcript.model_validate_json(transcript_path.read_text(encoding="utf8"))
    timeline = build_timeline(
        words=transcript.words, segment=Segment(from_word=from_word, to_word=to_word)
    )
    zoom_at_ms = words_to_clip_ms(
        word_indices=zoom_words or [], words=transcript.words, timeline=timeline
    )

    path = camera_path(
        faces=faces,
        frame_w=frame_width,
        frame_h=frame_height,
        duration_ms=timeline.duration_ms,
        zoom_at_ms=zoom_at_ms,
        cut_at_ms=timeline.video_cut_points_ms,
    )

    output.write_text(path.model_dump_json(indent=2), encoding="utf8")
    print(
        f"Camera path saved to {output} "
        f"({len(path.keyframes)} keyframes - {len(timeline.video_cut_points_ms)} cut bridges - "
        f"{len(zoom_at_ms)} zooms - {len(path.no_face)} stretches without a face)"
    )


@app.command("compose")
def compose_command(
    mezzanine: Annotated[Path, typer.Argument(help="Mezzanine from cut")],
    camera_path_file: Annotated[Path, typer.Argument(help="Camera path JSON from camera-path")],
    output: Annotated[Path, typer.Option(help="Output vertical video")] = Path("clip.mp4"),
) -> None:
    """Crop the mezzanine along the camera path into a 1080x1920 clip.

    Moves a crop window over MEZZANINE frame by frame, as CAMERA_PATH_FILE
    says, scales each window to 1080x1920 and writes the vertical clip to
    --output: H.264 at 30 fps, with the audio of the mezzanine copied as
    it is. Prints the number of frames.
    """
    path = CameraPath.model_validate_json(camera_path_file.read_text(encoding="utf8"))
    compose_clip(mezzanine_path=mezzanine, keyframes=path.keyframes, output_path=output)
    print(
        f"Vertical clip saved to {output} ({len(path.keyframes)} frames at {OUTPUT_W}x{OUTPUT_H})"
    )


@app.command("verify-clip")
def verify_clip_command(
    clip: Annotated[Path, typer.Argument(help="Vertical clip from compose")],
    mezzanine: Annotated[Path, typer.Argument(help="Mezzanine the clip was made from")],
    camera_path_file: Annotated[Path, typer.Argument(help="Camera path JSON used with compose")],
    faces_path: Annotated[Path, typer.Argument(help="Faces JSON from detect-faces")],
    transcript_path: Annotated[Path, typer.Argument(help="Transcript JSON used with cut")],
    from_word: Annotated[int, typer.Option("--from", help="First word index")],
    to_word: Annotated[int, typer.Option("--to", help="Last word index")],
) -> None:
    """Check that a vertical clip follows its camera path smoothly.

    Give it the same files and --from and --to used to make the clip.
    Checks the size (1080x1920), 30 fps, one frame per keyframe and audio
    within 1 frame of the video; that every frame shows its own crop
    window and each cut bridge lands on its cut; that the face is not cut
    more than 5 % per side (or evenly, when it does not fit); and that the
    window has no jumps over 20 px per frame and no wobbles. Prints one
    line per check and exits with code 1 if any fails.
    """
    path = CameraPath.model_validate_json(camera_path_file.read_text(encoding="utf8"))
    faces = TypeAdapter(list[FaceBox]).validate_json(faces_path.read_text(encoding="utf8"))
    transcript = Transcript.model_validate_json(transcript_path.read_text(encoding="utf8"))
    timeline = build_timeline(
        words=transcript.words, segment=Segment(from_word=from_word, to_word=to_word)
    )
    cut_frames = cut_at_frames(timeline.video_cut_points_ms, timeline.duration_ms)

    source = probe_video(mezzanine)

    checks = verify_clip(
        info=probe_video(clip),
        matches=match_frames(mezzanine, clip, path.keyframes),
        path=check_path(
            path.keyframes, faces, cut_frames, frame_w=source.width, frame_h=source.height
        ),
        cut_frames=cut_frames,
    )

    for check in checks:
        mark = "OK  " if check.ok else "FAIL"
        print(f"{mark} {check.name:<24} {check.value}  (limit {check.limit})")
    failed = sum(1 for check in checks if not check.ok)
    print(f"{len(checks) - failed} of {len(checks)} checks passed")
    if failed:
        raise typer.Exit(code=1)
