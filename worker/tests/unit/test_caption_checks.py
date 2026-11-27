import pytest

from content_engine.piece_types.clip.domain.camera_path import CropKeyframe
from content_engine.piece_types.clip.domain.caption_checks import (
    CaptionFrame,
    FontPick,
    box_gap,
    check_captions,
    check_fonts,
    highlight_plane,
    highlight_switches,
    read_ass_events,
    window_cover,
)
from content_engine.piece_types.clip.domain.captions_ass import (
    Box,
    CaptionPlan,
    CaptionStyle,
    ClipWord,
    captions_ass,
    face_box_px,
    plan_captions,
    words_in_clip,
)
from content_engine.piece_types.clip.domain.faces import FaceBox
from content_engine.piece_types.clip.domain.timeline import Cut, Timeline
from content_engine.shared.transcript import Word

STYLE = CaptionStyle()
FIGTREE = [FontPick(requested="Figtree", chosen="Figtree-Bold")]
FRAMES = 60
# One audio cut from 0 to 2000 ms, so clip time equals original time.
TIMELINE = Timeline(cuts=[Cut(start_ms=0, end_ms=2000)], video_cuts=[Cut(start_ms=0, end_ms=2000)])
# A 608x1080 window over a face whose bottom lands at 800 x 1920 / 1080 = 1422 px.
KEYFRAMES = [
    CropKeyframe(t_ms=round(f * 1000 / 30), x=656, y=0, w=608, h=1080) for f in range(FRAMES)
]
FACES = [FaceBox(t_ms=0, x=700, y=300, w=500, h=500, score=0.9)]


def word(i: int, text: str, start_ms: int, end_ms: int, filler: bool = False) -> Word:
    return Word(
        i=i,
        text=text,
        start_ms=start_ms,
        end_ms=end_ms,
        speaker="A",
        confidence=1.0,
        is_disfluency=filler,
    )


WORDS = [
    word(10, "And", 60, 300),
    word(11, "if", 360, 600),
    word(12, "your", 660, 900),
    word(13, "brand", 960, 1500),
]


def plan(style: CaptionStyle = STYLE) -> CaptionPlan:
    clip = words_in_clip(WORDS, TIMELINE)
    return plan_captions(clip, KEYFRAMES, FACES, cut_frame_ms=[], style=style)


def drawn_frames(late_word: int | None = None, highlight: bool = True) -> list[CaptionFrame]:
    # What libass would draw for `plan()`: a 518x110 caption, 84 % and 92.5 % on the
    # first two frames of the line, and the white word moving right one word at a time.
    the_plan = plan()
    line = the_plan.lines[0]
    frames: list[CaptionFrame] = []
    for frame in range(FRAMES):
        events = [e for e in the_plan.events if e.start_frame <= frame < e.end_frame]
        if late_word is not None and frame == the_plan.events[late_word].start_frame:
            events = [the_plan.events[late_word - 1]]
        if not events:
            frames.append(CaptionFrame(frame=frame, caption=None, highlight=None))
            continue
        scale = {0: 0.84, 1: 0.925}.get(frame - line.start_frame, 1.0)
        width, height = 518 * scale, 110 * scale
        x1, y1 = 540 - width / 2, line.center_y - height / 2
        position = events[0].word
        frames.append(
            CaptionFrame(
                frame=frame,
                caption=Box(x1=x1, y1=y1, x2=x1 + width - 1, y2=y1 + height - 1),
                highlight=Box(
                    x1=x1 + (20 + 120 * position) * scale,
                    y1=y1 + 30 * scale,
                    x2=x1 + (110 + 120 * position) * scale,
                    y2=y1 + 70 * scale,
                )
                if highlight
                else None,
            )
        )
    return frames


def run(**changes: object) -> dict[str, tuple[bool, str, bool]]:
    arguments: dict[str, object] = {
        "ass_text": captions_ass(plan(), STYLE),
        "words": WORDS,
        "timeline": TIMELINE,
        "frames": drawn_frames(),
        "fonts": FIGTREE,
        "keyframes": KEYFRAMES,
        "faces": FACES,
        "cut_frames": [],
    }
    arguments.update(changes)
    checks = check_captions(**arguments)  # type: ignore[arg-type]
    return {check.name: (check.ok, check.value, check.blocking) for check in checks}


def single_word_lines(widths: tuple[float, float], pop: bool) -> list[CaptionFrame]:
    # Two lines of one word, 10 frames each: the white word fills the box but its padding.
    frames: list[CaptionFrame] = []
    for frame in range(20):
        width = widths[frame // 10]
        scale = {0: 0.84, 1: 0.925}.get(frame % 10, 1.0) if pop else 1.0
        box_w, box_h = width * scale, 110 * scale
        x1, y1 = 540 - box_w / 2, 1600 - box_h / 2
        frames.append(
            CaptionFrame(
                frame=frame,
                caption=Box(x1=x1, y1=y1, x2=x1 + box_w - 1, y2=y1 + box_h - 1),
                highlight=Box(
                    x1=x1 + 18 * scale, y1=y1 + 30 * scale, x2=x1 + box_w - 18 * scale, y2=y1 + 70
                ),
            )
        )
    return frames


def test_read_ass_events_gets_words_highlight_and_names_back() -> None:
    events = read_ass_events(captions_ass(plan(), STYLE), STYLE)

    assert [(e.line, e.word_i, e.highlighted) for e in events] == [
        (0, 10, 0),
        (0, 11, 1),
        (0, 12, 2),
        (0, 13, 3),
    ]
    assert events[0].words == ["And", "if", "your", "brand"]


def test_highlight_switches_ignore_the_pop_and_count_each_word() -> None:
    # Words start on frames 2, 11, 20 and 29; the pop changes frames 2-4 but not the word.
    assert highlight_switches(drawn_frames()) == [2, 11, 20, 29]


def test_a_new_line_that_enters_small_is_a_switch() -> None:
    big = Box(x1=281, y1=1594, x2=798, y2=1703)
    small = Box(x1=330, y1=1600, x2=750, y2=1690)
    word_box = Box(x1=300, y1=1630, x2=407, y2=1671)
    same_place = Box(x1=346, y1=1630, x2=432, y2=1671)
    frames = [
        CaptionFrame(frame=0, caption=big, highlight=word_box),
        CaptionFrame(frame=1, caption=small, highlight=same_place),
    ]

    assert highlight_switches(frames) == [0, 1]


@pytest.mark.parametrize(
    ("widths", "pop"),
    [((316, 448), True), ((316, 336), False), ((316, 448), False)],
)
def test_one_word_lines_in_a_row_are_two_switches(widths: tuple[float, float], pop: bool) -> None:
    # "Exactly." then "Unfortunately,": the white word keeps the same place in its box,
    # and with the pop the new box at 84 % is about as big as the old one.
    assert highlight_switches(single_word_lines(widths, pop)) == [0, 10]


def test_clean_captions_pass_every_blocking_check() -> None:
    results = run()

    assert all(ok for ok, _, blocking in results.values() if blocking)
    assert len(results) == 5
    assert results["caption sync"][1] == "4 words; worst 6.7 ms"
    assert results["caption words"][1] == "4 shown of 4"


def test_a_word_one_frame_late_fails_sync() -> None:
    ok, value, _ = run(frames=drawn_frames(late_word=2))["caption sync"]

    assert not ok
    assert value == "4 words; worst 40.0 ms"


def test_captions_without_highlight_have_nothing_to_sync() -> None:
    style = CaptionStyle(highlight_mode="none")

    results = run(ass_text=captions_ass(plan(style), style), frames=drawn_frames(highlight=False))

    assert results["caption sync"][:2] == (True, "no highlighted words")


def test_a_filler_in_the_captions_fails_the_words_check() -> None:
    clip = [
        *words_in_clip(WORDS[:2], TIMELINE),
        ClipWord(i=99, text="um,", start_ms=600, end_ms=650, cut=0),
    ]
    clip += words_in_clip(WORDS[2:], TIMELINE)
    ass_text = captions_ass(plan_captions(clip, KEYFRAMES, FACES, [], STYLE), STYLE)
    with_filler = [*WORDS[:2], word(99, "um,", 600, 650, filler=True), *WORDS[2:]]

    ok, value, _ = run(ass_text=ass_text, words=with_filler)["caption words"]

    assert not ok
    assert value == "5 shown of 4; 1 not in the clip (99)"


def test_captions_over_the_face_fail() -> None:
    low_face = [FaceBox(t_ms=0, x=700, y=500, w=500, h=500, score=0.9)]

    ok, value, _ = run(faces=low_face)["captions clear of face"]

    assert not ok
    assert value.startswith("58 (2, 3, 4, 5, 6, 7, 8, 9, ...) over the face")


@pytest.mark.parametrize(
    "chosen",
    ["Arial-BoldMT", "Figtree-Regular", None],
)
def test_a_fallback_or_regular_font_fails(chosen: str | None) -> None:
    check = check_fonts([FontPick(requested="Figtree", chosen=chosen)], STYLE)

    assert not check.ok
    assert check.limit == "only Figtree Bold"


def test_a_font_of_another_family_fails_even_if_libass_found_it() -> None:
    # Phudu is a forbidden font for Guidepost: the ASS asking for it must not pass.
    assert not check_fonts([FontPick(requested="Phudu", chosen="Phudu-Bold")], STYLE).ok
    assert not check_fonts([], STYLE).ok
    assert check_fonts(FIGTREE, STYLE).ok


def test_leaving_the_safe_zone_is_only_a_warning() -> None:
    ok, _, blocking = run()["captions in safe zone"]

    # The line sits below a face whose bottom is at 1422 px, deeper than y 1520.
    assert (ok, blocking) == (False, False)


def test_face_box_in_output_pixels() -> None:
    box = face_box_px(KEYFRAMES[0], FACES[0])

    # x: (700 - 656) x 1080 / 608 = 78.2; bottom: 800 x 1920 / 1080 - 1 = 1421.2.
    assert (round(box.x1, 1), round(box.y2, 1)) == (78.2, 1421.2)


def test_box_gap_is_negative_when_boxes_overlap() -> None:
    a = Box(x1=0, y1=0, x2=99, y2=99)

    assert box_gap(a, Box(x1=0, y1=120, x2=99, y2=199)) == 20
    assert box_gap(a, Box(x1=0, y1=100, x2=99, y2=199)) == 0
    assert box_gap(a, Box(x1=50, y1=50, x2=150, y2=150)) < 0


def test_window_cover_is_clipped_to_the_window() -> None:
    window = CropKeyframe(t_ms=0, x=820, y=0, w=608, h=1080)

    assert window_cover(Box(x1=0, y1=1850, x2=1079, y2=1919), window) == (0, 1038, 608, 1080)


def test_highlight_plane_needs_a_brighter_channel() -> None:
    assert highlight_plane(STYLE) == ("b", 148)
    with pytest.raises(ValueError, match="brighter"):
        highlight_plane(CaptionStyle(highlight_color="#000000"))
