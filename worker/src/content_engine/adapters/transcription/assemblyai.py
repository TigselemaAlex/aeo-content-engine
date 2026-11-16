from pathlib import Path

import assemblyai as aai


def transcribe(audio_path: Path, api_key: str, glossary: list[str]) -> str:
    aai.settings.api_key = api_key
    config = aai.TranscriptionConfig(
        disfluencies=True, speaker_labels=True, keyterms_prompt=glossary
    )
    transcriber = aai.Transcriber(config=config)
    transcript = transcriber.transcribe(str(audio_path))

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(transcript.error)
    return transcript.text or ""
