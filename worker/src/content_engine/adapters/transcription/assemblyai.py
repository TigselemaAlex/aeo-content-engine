from pathlib import Path
from typing import Any, cast

import assemblyai as aai

from content_engine.modules.ingest.domain.transcript import Transcript, Word, is_filler_word


def request_transcription(audio_path: Path, api_key: str, glossary: list[str]) -> dict[str, Any]:
    aai.settings.api_key = api_key
    config = aai.TranscriptionConfig(
        disfluencies=True, speaker_labels=True, keyterms_prompt=glossary
    )
    transcriber = aai.Transcriber(config=config)
    transcript = transcriber.transcribe(str(audio_path))

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(transcript.error)
    response = cast(dict[str, Any] | None, transcript.json_response)  # pyright: ignore[reportUnknownMemberType]
    if not response:
        raise RuntimeError("No response from transcript")
    return response


def to_transcript(raw: dict[str, Any]) -> Transcript:
    return Transcript(
        provider="assemblyai",
        provider_ref=raw["id"],
        language=raw["language_code"],
        duration_ms=round(raw["audio_duration"] * 1000),
        text=raw["text"],
        words=[
            Word(
                start_ms=w["start"],
                end_ms=w["end"],
                confidence=w["confidence"],
                speaker=w.get("speaker"),
                is_disfluency=is_filler_word(w["text"]),
                text=w["text"],
                i=i,
            )
            for i, w in enumerate(raw["words"])
        ],
    )


def transcribe(audio_path: Path, api_key: str, glossary: list[str]) -> Transcript:
    return to_transcript(
        raw=request_transcription(audio_path=audio_path, api_key=api_key, glossary=glossary)
    )
