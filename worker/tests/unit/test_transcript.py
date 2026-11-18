import pytest
from pydantic import ValidationError

from content_engine.modules.ingest.domain.transcript import is_filler_word
from content_engine.shared.transcript import Word


def test_word_accepts_valid_values() -> None:
    word = Word(
        i=0, text="AEO", start_ms=200, end_ms=500, speaker="A", confidence=0.9, is_disfluency=False
    )

    assert word.i == 0
    assert word.text == "AEO"
    assert word.start_ms == 200
    assert word.end_ms == 500
    assert word.speaker == "A"
    assert word.confidence == 0.9
    assert not word.is_disfluency


def test_word_rejects_negative_start() -> None:
    with pytest.raises(ValidationError):
        Word(
            i=0,
            text="AEO",
            start_ms=-200,
            end_ms=500,
            speaker="A",
            confidence=0.9,
            is_disfluency=False,
        )


def test_word_rejects_end_before_start() -> None:
    with pytest.raises(ValidationError):
        Word(
            i=0,
            text="AEO",
            start_ms=500,
            end_ms=100,
            speaker="A",
            confidence=0.9,
            is_disfluency=False,
        )


def test_filler_word_is_detected_with_punctuation() -> None:
    assert is_filler_word("Um,")


def test_normal_word_is_not_a_filler() -> None:
    assert not is_filler_word("AEO")


def test_word_that_starts_like_a_filler_is_not_one() -> None:
    assert not is_filler_word("umbrella")
