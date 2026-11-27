import pytest

from content_engine.piece_types.clip.domain.camera_path import CropKeyframe
from content_engine.piece_types.clip.domain.captions_ass import (
    CaptionStyle,
    ClipWord,
    ass_color,
    ass_override_color,
    ass_time,
    caption_text,
    captions_ass,
    group_words,
    hex_color,
    line_center_y,
    plan_captions,
    pop_tags,
    read_ass_style,
    split_into_phrases,
    split_phrase,
    words_in_clip,
)
from content_engine.piece_types.clip.domain.faces import FaceBox
from content_engine.piece_types.clip.domain.timeline import Segment, build_timeline, ms_to_frame
from content_engine.shared.transcript import Word

STYLE = CaptionStyle()


def make_words(texts: list[str], fillers: tuple[int, ...] = ()) -> list[Word]:
    # One word per second, each 500 ms long.
    return [
        Word(
            i=k,
            text=text,
            start_ms=k * 1000,
            end_ms=k * 1000 + 500,
            speaker="A",
            confidence=1.0,
            is_disfluency=k in fillers,
        )
        for k, text in enumerate(texts)
    ]


def clip_words(
    texts: list[str], start_ms: int = 0, step_ms: int = 300, cut: int = 0
) -> list[ClipWord]:
    return [
        ClipWord(
            i=k,
            text=text,
            start_ms=start_ms + k * step_ms,
            end_ms=start_ms + k * step_ms + 250,
            cut=cut,
        )
        for k, text in enumerate(texts)
    ]


def still_path(frames: int) -> list[CropKeyframe]:
    return [
        CropKeyframe(t_ms=round(f * 1000 / 30), x=656, y=0, w=608, h=1080) for f in range(frames)
    ]


def test_words_in_clip_drops_fillers_and_maps_times() -> None:
    words = make_words(["one", "two", "um", "three", "four", "five"], fillers=(2,))
    timeline = build_timeline(words, Segment(from_word=0, to_word=5))

    kept = words_in_clip(words, timeline)

    assert [w.text for w in kept] == ["one", "two", "three", "four", "five"]
    # Word 3 starts 60 ms into the second cut (2940-5620), which starts at 1620 ms in the clip.
    assert (kept[2].start_ms, kept[2].end_ms, kept[2].cut) == (1680, 2180, 1)
    assert kept[0].cut == 0


def test_words_in_clip_drops_words_outside_the_cuts() -> None:
    words = make_words(["a", "b", "c", "d"])
    timeline = build_timeline(words, Segment(from_word=1, to_word=2))

    assert [w.i for w in words_in_clip(words, timeline)] == [1, 2]


def test_phrases_break_at_punctuation_cuts_and_long_pauses() -> None:
    words = [
        ClipWord(i=0, text="Hello,", start_ms=0, end_ms=200, cut=0),
        ClipWord(i=1, text="this", start_ms=300, end_ms=500, cut=0),
        ClipWord(i=2, text="is", start_ms=600, end_ms=700, cut=1),
        ClipWord(i=3, text="long", start_ms=800, end_ms=900, cut=1),
        ClipWord(i=4, text="pause", start_ms=1500, end_ms=1600, cut=1),
    ]

    phrases = split_into_phrases(words, pause_max_ms=500)

    assert [[w.text for w in phrase] for phrase in phrases] == [
        ["Hello,"],
        ["this"],
        ["is", "long"],
        ["pause"],
    ]


def test_long_phrase_is_split_in_the_fewest_even_lines() -> None:
    # "SEO was about ranking on Google," from the test recording: 32 characters, 6 words.
    phrase = clip_words(["SEO", "was", "about", "ranking", "on", "Google,"])

    lines = split_phrase(phrase, max_words=4, max_chars=22)

    # Two lines; 13 + 18 characters beats 21 + 10 (greedy) because its longest is shorter.
    assert [" ".join(w.text for w in line) for line in lines] == [
        "SEO was about",
        "ranking on Google,",
    ]


def test_lines_respect_the_word_limit() -> None:
    phrase = clip_words(["a", "b", "c", "d", "e", "f", "g", "h", "i"])

    lines = split_phrase(phrase, max_words=4, max_chars=22)

    assert [len(line) for line in lines] == [3, 3, 3]


def test_a_word_longer_than_the_limit_gets_its_own_line() -> None:
    phrase = clip_words(["the", "antidisestablishmentarianism", "era"])

    lines = split_phrase(phrase, max_words=4, max_chars=22)

    assert [[w.text for w in line] for line in lines] == [
        ["the"],
        ["antidisestablishmentarianism"],
        ["era"],
    ]


def test_group_words_joins_phrases_and_lines() -> None:
    words = clip_words(["you", "basically", "don't", "exist.", "My", "name"])

    lines = group_words(words, STYLE)

    # "you basically don't exist." has 26 characters: two lines of 13 and 12.
    assert [" ".join(w.text for w in line) for line in lines] == [
        "you basically",
        "don't exist.",
        "My name",
    ]


def test_ms_to_frame_rounds_the_clip_time() -> None:
    # 365 ms is frame 10.95 -> 11; 17050 ms is 511.5 -> 512 (Python rounds ties to even).
    assert ms_to_frame(365) == 11
    assert ms_to_frame(17050) == 512
    assert ms_to_frame(24150) == 724


def test_plan_gives_each_word_its_frames_back_to_back() -> None:
    words = clip_words(["And", "if", "your", "brand"], start_ms=60, step_ms=300)

    plan = plan_captions(words, still_path(60), faces=[], cut_frame_ms=[], style=STYLE)

    assert [(e.word, e.start_frame, e.end_frame) for e in plan.events] == [
        (0, 2, 11),
        (1, 11, 20),
        (2, 20, 29),
        (3, 29, 60),
    ]
    assert (plan.lines[0].start_frame, plan.lines[0].end_frame) == (2, 60)
    assert plan.skipped == []


def test_a_word_sharing_its_frame_with_the_next_is_skipped() -> None:
    # "a" lasts 16 ms: 1000 ms and 1016 ms both round to frame 30.
    words = [
        ClipWord(i=0, text="pick", start_ms=900, end_ms=990, cut=0),
        ClipWord(i=1, text="a", start_ms=1000, end_ms=1016, cut=0),
        ClipWord(i=2, text="few", start_ms=1016, end_ms=1200, cut=0),
    ]

    plan = plan_captions(words, still_path(60), faces=[], cut_frame_ms=[], style=STYLE)

    assert plan.skipped == [1]
    assert [e.word for e in plan.events] == [0, 2]
    assert [w.text for w in plan.lines[0].words] == ["pick", "a", "few"]


def test_a_one_word_line_without_frames_joins_the_next_line() -> None:
    # "Yes." lasts 15 ms and ends its phrase: 990 ms and 1005 ms both round to frame 30.
    words = [
        ClipWord(i=0, text="Yes.", start_ms=990, end_ms=1005, cut=0),
        ClipWord(i=1, text="So", start_ms=1005, end_ms=1200, cut=0),
        ClipWord(i=2, text="we", start_ms=1300, end_ms=1400, cut=0),
    ]

    plan = plan_captions(words, still_path(60), faces=[], cut_frame_ms=[], style=STYLE)

    assert [[w.text for w in line.words] for line in plan.lines] == [["Yes.", "So", "we"]]
    assert plan.skipped == [0]
    assert [e.word for e in plan.events] == [1, 2]


def test_a_last_line_without_frames_joins_the_previous_line() -> None:
    # "Bye." starts in the last half frame of a 30-frame clip: round(985 x 30 / 1000) = 30.
    words = [
        ClipWord(i=0, text="See", start_ms=300, end_ms=500, cut=0),
        ClipWord(i=1, text="you.", start_ms=600, end_ms=900, cut=0),
        ClipWord(i=2, text="Bye.", start_ms=985, end_ms=995, cut=0),
    ]

    plan = plan_captions(words, still_path(30), faces=[], cut_frame_ms=[], style=STYLE)

    assert [[w.text for w in line.words] for line in plan.lines] == [["See", "you.", "Bye."]]


def test_line_goes_below_the_lowest_face_of_its_frames() -> None:
    keyframes = still_path(30)
    # A face whose bottom moves from y 800 to 825 in the mezzanine: 825 x 1920 / 1080 = 1466.7.
    faces = [
        FaceBox(t_ms=0, x=900, y=300, w=500, h=500, score=0.9),
        FaceBox(t_ms=900, x=900, y=325, w=500, h=500, score=0.9),
    ]

    center = line_center_y(0, 30, keyframes, faces, cut_frame_ms=[], style=STYLE)

    # Top = ceil(1466.7) + 20 = 1487; the box is 72 + 2 x 18 = 108 tall, so its center is 1541.
    assert center == 1487 + 54


def test_line_never_leaves_the_frame() -> None:
    faces = [FaceBox(t_ms=0, x=900, y=500, w=580, h=580, score=0.9)]

    center = line_center_y(0, 10, still_path(10), faces, cut_frame_ms=[], style=STYLE)

    assert center == 1920 - 108 + 54


def test_line_without_a_face_sits_on_the_safe_zone() -> None:
    center = line_center_y(0, 10, still_path(10), faces=[], cut_frame_ms=[], style=STYLE)

    # Bottom edge at 1920 - 400 = 1520: top 1412, center 1466.
    assert center == 1466


def test_ass_colors_are_blue_green_red() -> None:
    assert ass_color("#FF7B2A") == "&H002A7BFF"
    assert ass_override_color("#FF7B2A") == "&H2A7BFF&"
    assert ass_override_color("#ffffff") == "&HFFFFFF&"


def test_ass_time_is_half_a_frame_early_in_centiseconds() -> None:
    # Frame 11 starts at 366.7 ms; half a frame before is 350 ms.
    assert ass_time(11) == "0:00:00.35"
    assert ass_time(0) == "0:00:00.00"
    assert ass_time(1004) == "0:00:33.45"
    assert ass_time(30 * 3725) == "1:02:04.98"


def test_pop_tags_continue_the_entrance_across_events() -> None:
    assert pop_tags(0, STYLE) == "\\fscx80.0\\fscy80.0\\t(0,80,\\fscx100\\fscy100)"
    # 33 ms in: 80 + 20 x 33 / 80 = 88.25 %, and 47 ms of growth left.
    assert pop_tags(33, STYLE) == "\\fscx88.2\\fscy88.2\\t(0,47,\\fscx100\\fscy100)"
    assert pop_tags(80, STYLE) == ""


def test_caption_text_removes_ass_tag_characters() -> None:
    assert caption_text("{weird}\\word") == "weirdword"


def test_caption_text_keeps_a_word_with_a_space_as_one_word() -> None:
    assert caption_text("10 000") == "10 000"


def test_words_left_empty_are_not_shown() -> None:
    words = make_words(["one", "{}", "three"])
    timeline = build_timeline(words, Segment(from_word=0, to_word=2))

    assert [w.text for w in words_in_clip(words, timeline)] == ["one", "three"]


def test_the_style_is_read_back_from_the_ass_file() -> None:
    style = CaptionStyle(font_name="Figtree", size_px=64, highlight_color="#FFD000")
    plan = plan_captions(
        clip_words(["Hi"], start_ms=60), still_path(30), faces=[], cut_frame_ms=[], style=style
    )

    read = read_ass_style(captions_ass(plan, style))

    assert (read.font_name, read.size_px, read.bold, read.box_padding_px) == (
        "Figtree",
        64,
        True,
        18,
    )
    assert (read.text_color, read.highlight_color, read.box_color) == (
        "#FF7B2A",
        "#FFD000",
        "#000000",
    )


def test_hex_color_reverses_ass_color() -> None:
    assert hex_color("&H002A7BFF") == "#FF7B2A"
    assert hex_color("&H2A7BFF&") == "#FF7B2A"


def test_captions_ass_writes_one_dialogue_per_event() -> None:
    words = clip_words(["And", "if"], start_ms=60, step_ms=300)
    plan = plan_captions(words, still_path(30), faces=[], cut_frame_ms=[], style=STYLE)

    text = captions_ass(plan, STYLE)

    assert "PlayResX: 1080\nPlayResY: 1920" in text
    assert "YCbCr Matrix: TV.709" in text
    assert (
        "Style: Caption,Figtree,72,&H002A7BFF,&H00FFFFFF,&H00000000,&H00000000,"
        "-1,0,0,0,100,100,0,0,3,18,0,5,0,0,0,1"
    ) in text
    dialogues = [row for row in text.splitlines() if row.startswith("Dialogue:")]
    assert dialogues == [
        "Dialogue: 0,0:00:00.05,0:00:00.35,Caption,0:0,0,0,0,,{\\an5\\pos(540,1466)"
        "\\fscx80.0\\fscy80.0\\t(0,80,\\fscx100\\fscy100)}{\\1c&HFFFFFF&}And{\\1c&H2A7BFF&} if",
        "Dialogue: 0,0:00:00.35,0:00:00.98,Caption,0:1,0,0,0,,{\\an5\\pos(540,1466)}"
        "And {\\1c&HFFFFFF&}if{\\1c&H2A7BFF&}",
    ]


@pytest.mark.parametrize(
    ("mode", "keywords", "highlighted"),
    [("word", frozenset[int](), 2), ("keywords", frozenset({1}), 1), ("none", frozenset[int](), 0)],
)
def test_highlight_modes(mode: str, keywords: frozenset[int], highlighted: int) -> None:
    style = CaptionStyle.model_validate({"highlight_mode": mode})
    words = clip_words(["And", "if"], start_ms=60, step_ms=300)
    plan = plan_captions(words, still_path(30), faces=[], cut_frame_ms=[], style=style)

    text = captions_ass(plan, style, keywords)

    assert text.count("{\\1c&HFFFFFF&}") == highlighted
