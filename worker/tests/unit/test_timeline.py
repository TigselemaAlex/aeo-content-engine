import pytest
from pydantic import ValidationError

from content_engine.piece_types.clip.domain.timeline import (
    Cut,
    Segment,
    Timeline,
    segment_to_cut,
    split_out_filters,
)
from content_engine.shared.transcript import Word


def make_words(count: int, fillers: tuple[int, ...] = ()) -> list[Word]:
    return [
        Word(
            i=k,
            text="um" if k in fillers else f"word{k}",
            start_ms=k * 1000,
            end_ms=k * 1000 + 500,
            speaker="A",
            confidence=1.0,
            is_disfluency=k in fillers,
        )
        for k in range(count)
    ]


def test_segment_with_invalid_order() -> None:
    with pytest.raises(ValidationError, match="to_word must not be lower than from_word"):
        Segment(from_word=20, to_word=10)


def test_cut_with_invalid_times_order() -> None:
    with pytest.raises(ValidationError, match="end_ms must be after start_ms"):
        Cut(start_ms=1000, end_ms=1000)


def test_timeline_duration() -> None:
    timeline = Timeline(cuts=[Cut(start_ms=0, end_ms=1000), Cut(start_ms=3000, end_ms=3500)])

    assert timeline.duration_ms == 1500


def test_segment_to_cut_uses_first_word_start_and_last_word_end() -> None:
    words = make_words(25)
    cut = segment_to_cut(segment=Segment(from_word=10, to_word=20), words=words)
    assert cut == Cut(start_ms=10000, end_ms=20500)


def test_segment_to_cut_accepts_last_word() -> None:
    words = make_words(25)

    cut = segment_to_cut(segment=Segment(from_word=20, to_word=24), words=words)
    assert cut.end_ms == 24500


def test_segment_to_cut_rejects_segment_outside_transcript() -> None:
    words = make_words(25)

    with pytest.raises(ValueError, match="only has indices 0 to 24"):
        segment_to_cut(segment=Segment(from_word=20, to_word=25), words=words)


@pytest.mark.parametrize(
    ("fillers", "expected"),
    [
        ((4,), [(0, 3), (5, 9)]),
        ((), [(0, 9)]),
        ((0, 9), [(1, 8)]),
        ((4, 5), [(0, 3), (6, 9)]),
        (tuple(range(10)), []),
    ],
    ids=[
        "filler_in_middle",
        "no_fillers",
        "fillers_at_edges",
        "consecutive_fillers",
        "only_fillers",
    ],
)
def test_split_out_fillers(fillers: tuple[int, ...], expected: list[tuple[int, int]]) -> None:
    words = make_words(count=10, fillers=fillers)

    pieces = split_out_filters(segment=Segment(from_word=0, to_word=9), words=words)

    assert [(piece.from_word, piece.to_word) for piece in pieces] == expected
