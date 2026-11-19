import pytest
from pydantic import ValidationError

from content_engine.piece_types.clip.domain.timeline import (
    Cut,
    Segment,
    Timeline,
    segment_to_cut,
    segment_to_padded_cut,
    split_at_long_pauses,
    split_out_fillers,
)
from content_engine.shared.transcript import Word


def make_word(i: int, start_ms: int, end_ms: int, filler: bool = False) -> Word:
    return Word(
        i=i,
        text="um" if filler else f"word{i}",
        start_ms=start_ms,
        end_ms=end_ms,
        speaker="A",
        confidence=1.0,
        is_disfluency=filler,
    )


def make_words(count: int, fillers: tuple[int, ...] = ()) -> list[Word]:
    return [
        make_word(
            i=k,
            start_ms=k * 1000,
            end_ms=k * 1000 + 500,
            filler=k in fillers,
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

    pieces = split_out_fillers(segment=Segment(from_word=0, to_word=9), words=words)

    assert [(piece.from_word, piece.to_word) for piece in pieces] == expected


def words_with_long_pause_after_1() -> list[Word]:
    return [
        make_word(i=0, start_ms=0, end_ms=500),
        make_word(i=1, start_ms=1000, end_ms=1500),
        make_word(i=2, start_ms=3500, end_ms=4000),  # 2000ms after word 1
        make_word(i=3, start_ms=4500, end_ms=5000),
    ]


def test_split_at_long_pauses_splits_on_2s_gap() -> None:
    words = words_with_long_pause_after_1()

    pieces = split_at_long_pauses(
        segment=Segment(from_word=0, to_word=3), words=words, pause_max_ms=500
    )

    assert pieces == [Segment(from_word=0, to_word=1), Segment(from_word=2, to_word=3)]


def test_split_at_long_pauses_keeps_gap_equal_to_max() -> None:
    words = make_words(4)

    pieces = split_at_long_pauses(
        segment=Segment(from_word=0, to_word=3), words=words, pause_max_ms=500
    )

    assert pieces == [Segment(from_word=0, to_word=3)]


def test_split_at_long_pauses_respects_emphasis_pause() -> None:
    words = words_with_long_pause_after_1()

    pieces = split_at_long_pauses(
        segment=Segment(from_word=0, to_word=3),
        words=words,
        pause_max_ms=500,
        keep_pauses_after=(1,),
    )

    assert pieces == [Segment(from_word=0, to_word=3)]


def test_segment_to_padded_cut_adds_full_padding() -> None:
    words = make_words(5)

    cut = segment_to_padded_cut(segment=Segment(from_word=1, to_word=2), words=words)

    assert cut == Cut(start_ms=940, end_ms=2620)


def test_segment_to_padded_cut_stops_at_close_neighbors() -> None:
    words = [
        make_word(i=0, start_ms=0, end_ms=500),
        make_word(i=1, start_ms=530, end_ms=1000),
        make_word(i=2, start_ms=1030, end_ms=1500),
    ]

    cut = segment_to_padded_cut(segment=Segment(from_word=1, to_word=1), words=words)

    assert cut == Cut(start_ms=500, end_ms=1030)


def test_segment_to_padded_cut_at_transcript_edges() -> None:
    words = [make_word(i=0, start_ms=30, end_ms=500)]

    cut = segment_to_padded_cut(segment=Segment(from_word=0, to_word=0), words=words)

    assert cut == Cut(start_ms=0, end_ms=620)


@pytest.mark.parametrize(
    ("original_ms", "expected"),
    [(500, 500), (2500, 1500), (1500, None), (1000, 1000)],
    ids=["first_cut", "second_cut", "in_removed_pause", "end_of_first_cut"],
)
def test_to_clip_ms_with_pause_dropped(original_ms: int, expected: int | None) -> None:
    timeline = Timeline(cuts=[Cut(start_ms=0, end_ms=1000), Cut(start_ms=2000, end_ms=3500)])

    assert timeline.to_clip_ms(original_ms=original_ms) == expected


@pytest.mark.parametrize(
    ("original_ms", "expected"),
    [(5500, 500), (500, 1500)],
    ids=["hook_placed_first", "start_placed_after_hook"],
)
def test_to_clip_ms_follows_cut_order(original_ms: int, expected: int) -> None:
    timeline = Timeline(cuts=[Cut(start_ms=5000, end_ms=6000), Cut(start_ms=0, end_ms=1000)])

    assert timeline.to_clip_ms(original_ms=original_ms) == expected
