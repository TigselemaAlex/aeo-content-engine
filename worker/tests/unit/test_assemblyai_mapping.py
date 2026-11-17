from content_engine.adapters.transcription.assemblyai import to_transcript

RAW_RESPONSE = {
    "id": "test-id",
    "language_code": "en_us",
    "audio_duration": 2.5,
    "text": "Um, AEO works.",
    "words": [
        {"text": "Um,", "start": 100, "end": 300, "confidence": 0.8, "speaker": "A"},
        {"text": "AEO", "start": 400, "end": 700, "confidence": 0.95, "speaker": "A"},
        {"text": "works.", "start": 750, "end": 1100, "confidence": 0.99, "speaker": "A"},
    ],
}


def test_duration_is_converted_to_milliseconds() -> None:
    transcript = to_transcript(raw=RAW_RESPONSE)
    assert transcript.duration_ms == 2500


def test_words_are_numbered_in_order() -> None:
    transcript = to_transcript(raw=RAW_RESPONSE)
    assert [w.i for w in transcript.words] == [0, 1, 2]


def test_word_times_are_mapped() -> None:
    transcript = to_transcript(raw=RAW_RESPONSE)
    word = transcript.words[1]
    assert word.start_ms == 400
    assert word.end_ms == 700


def test_filler_are_marked() -> None:
    transcript = to_transcript(raw=RAW_RESPONSE)
    filler_word = transcript.words[0]
    not_filler_word = transcript.words[1]
    assert filler_word.is_disfluency
    assert not not_filler_word.is_disfluency


def test_provider_reference_is_kept() -> None:
    transcript = to_transcript(raw=RAW_RESPONSE)
    assert transcript.provider == "assemblyai"
    assert transcript.provider_ref == "test-id"
