"""Transcribe audio with AssemblyAI and turn its response into the worker's `Transcript`.

Only this file reads AssemblyAI's raw response; the rest of the worker sees `Transcript`
and `Word` (docs/01 §7). Word times are milliseconds of the audio file, the same clock as
the video it was extracted from.
"""

from pathlib import Path
from typing import Any, cast

import assemblyai as aai

from content_engine.modules.ingest.domain.transcript import is_filler_word
from content_engine.shared.transcript import Transcript, Word


def request_transcription(audio_path: Path, api_key: str, glossary: list[str]) -> dict[str, Any]:
    """Send an audio file to AssemblyAI, wait for the transcript and return its raw JSON.

    Uses AssemblyAI's default model with `disfluencies` on, so fillers like "um" and "uh"
    are kept instead of removed, speaker labels on, and the glossary as `keyterms_prompt`,
    so brand names come out spelled right (docs/03 §3, docs/00 "Muletillas y glosario").
    The SDK uploads the file and blocks until the transcript is ready. The API key is set
    on the SDK's global settings (`aai.settings.api_key`), so it stays set for later calls
    in the same process.

    Args:
        audio_path: Audio file to send, for example the `.m4a` from `extract_audio`.
        api_key: AssemblyAI API key.
        glossary: Terms that must be written exactly so, for example `["AEO", "ChatGPT"]`.
            In the pipeline it is the client's `voice.glossary` (docs/02 §4.2).

    Returns:
        AssemblyAI's transcript JSON, with `id`, `language_code`, `audio_duration` (in
        seconds), `text` and `words` (times in milliseconds). `to_transcript` turns it
        into a `Transcript`.

    Raises:
        RuntimeError: If AssemblyAI reports the transcript as failed (the message is its
            error), or if the response comes back empty.
    """
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
    """Convert AssemblyAI's raw transcript JSON into a `Transcript`.

    Keeps AssemblyAI's `id` as `provider_ref`, its `language_code` as `language` and its
    `text`. The audio length goes from seconds to milliseconds:
    `round(audio_duration x 1000)` (s -> ms). Each word keeps its start and end (already
    in milliseconds), confidence and speaker (None if missing), gets its position in the
    list as `i`, and gets `is_disfluency` from the filler list of `ingest`, because
    AssemblyAI does not mark fillers (docs/03 §3, docs/00 "Muletillas y glosario").

    Args:
        raw: The JSON from `request_transcription`, or a saved copy of it.

    Returns:
        The transcript, with `provider` "assemblyai" and the words numbered from 0 in
        the order AssemblyAI gave them.

    Raises:
        KeyError: If a field is missing: `id`, `language_code`, `audio_duration`,
            `text` or `words`, or a word's `text`, `start`, `end` or `confidence`.
        pydantic.ValidationError: If a value breaks the rules of `Transcript` or `Word`,
            for example a word that ends before it starts or a confidence above 1.

    Example:
        With `audio_duration` 2.5 s, `duration_ms` is round(2.5 x 1000) = 2500. The
        words "Um,", "AEO" and "works." get `i` 0, 1 and 2, and only "Um," is marked as
        a filler: the punctuation around a word is ignored when matching the list.
    """
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
    """Transcribe an audio file with AssemblyAI and return it as a `Transcript`.

    Calls `request_transcription` and passes its JSON to `to_transcript`: fillers kept
    and marked, speakers labeled, the glossary sent as vocabulary.

    Args:
        audio_path: Audio file to send, for example the `.m4a` from `extract_audio`.
        api_key: AssemblyAI API key.
        glossary: Terms that must be written exactly so, for example `["AEO", "ChatGPT"]`.

    Returns:
        The transcript, with word times in milliseconds of the audio file.

    Raises:
        RuntimeError: If AssemblyAI reports the transcript as failed, or if the response
            comes back empty.

    Example:
        The audio of the test recording gave 309 words over 198000 ms, 2 of them fillers
        (`tests/fixtures/example-transcript.json`).
    """
    return to_transcript(
        raw=request_transcription(audio_path=audio_path, api_key=api_key, glossary=glossary)
    )
