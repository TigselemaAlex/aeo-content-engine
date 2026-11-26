import pytest

from content_engine.piece_types.clip.domain.camera_path import CropKeyframe
from content_engine.piece_types.clip.domain.ffmpeg_args import (
    build_compose_args,
    build_extract_args,
    compose_filter,
    concat_filter,
    ffmpeg_major_version,
    ffmpeg_supports_variable_crop,
    frame_counts,
    input_args,
    seconds,
)
from content_engine.piece_types.clip.domain.timeline import Cut, Timeline


def test_seconds_formats_ms_with_three_decimals() -> None:
    assert seconds(0) == "0.000"
    assert seconds(2940) == "2.940"
    assert seconds(61234) == "61.234"


def test_input_args_seeks_to_cut_and_reads_its_duration() -> None:
    cut = Cut(start_ms=2940, end_ms=5620)

    assert input_args(source="video.mp4", cut=cut) == [
        "-ss",
        "2.940",
        "-t",
        "2.680",
        "-i",
        "video.mp4",
    ]


def test_input_args_can_read_a_little_more() -> None:
    cut = Cut(start_ms=2940, end_ms=5620)

    assert input_args(source="video.mp4", cut=cut, extra_ms=100)[3] == "2.780"


def test_frame_counts_round_where_each_cut_ends() -> None:
    # The first three video cuts of the test recording: 3206, 2350 and 1131 ms.
    # They end at 3206, 5556 and 6687 ms -> frames 96.18, 166.68 and 200.61 -> 96, 167, 201.
    cuts = [
        Cut(start_ms=0, end_ms=3206),
        Cut(start_ms=0, end_ms=2350),
        Cut(start_ms=0, end_ms=1131),
    ]

    assert frame_counts(cuts) == [96, 71, 34]


def test_frame_counts_do_not_drift() -> None:
    # Ten cuts of 1010 ms: 30.3 frames each. Rounding each one alone gives 30 * 10 = 300
    # frames (10 s), losing 3 frames; rounding the running total gives 303 (10.1 s).
    cuts = [Cut(start_ms=0, end_ms=1010)] * 10

    assert sum(frame_counts(cuts)) == 303


def test_frame_counts_reject_a_cut_shorter_than_one_frame() -> None:
    with pytest.raises(ValueError, match="less than one frame"):
        frame_counts([Cut(start_ms=0, end_ms=1000), Cut(start_ms=0, end_ms=10)])


def test_concat_filter_joins_video_and_audio_separately() -> None:
    assert concat_filter(frame_counts=[53, 76]) == (
        "[0:v]setpts=PTS-STARTPTS,fps=30,trim=end_frame=53,setpts=PTS-STARTPTS[v0];"
        "[2:v]setpts=PTS-STARTPTS,fps=30,trim=end_frame=76,setpts=PTS-STARTPTS[v1];"
        "[v0][v1]concat=n=2:v=1:a=0[v];"
        "[1:a][3:a]concat=n=2:v=0:a=1[a]"
    )


def test_concat_filter_with_one_cut() -> None:
    assert concat_filter(frame_counts=[30]) == (
        "[0:v]setpts=PTS-STARTPTS,fps=30,trim=end_frame=30,setpts=PTS-STARTPTS[v0];"
        "[v0]concat=n=1:v=1:a=0[v];"
        "[1:a]concat=n=1:v=0:a=1[a]"
    )


def test_build_extract_args_cuts_video_and_audio_and_joins_them() -> None:
    timeline = Timeline(
        cuts=[Cut(start_ms=0, end_ms=1620), Cut(start_ms=2940, end_ms=5620)],
        video_cuts=[Cut(start_ms=0, end_ms=1753), Cut(start_ms=3073, end_ms=5620)],
    )

    args = build_extract_args(source="video.mp4", timeline=timeline, output="mezzanine.mp4")

    # Video cuts read 100 ms more (1.853 and 2.647 s) and are trimmed to 53 and 76 frames:
    # 1753 ms -> 52.59 -> 53, and 1753 + 2547 = 4300 ms -> 129 -> 129 - 53 = 76.
    assert args == [
        "-y",
        "-ss",
        "0.000",
        "-t",
        "1.853",
        "-i",
        "video.mp4",
        "-ss",
        "0.000",
        "-t",
        "1.620",
        "-i",
        "video.mp4",
        "-ss",
        "3.073",
        "-t",
        "2.647",
        "-i",
        "video.mp4",
        "-ss",
        "2.940",
        "-t",
        "2.680",
        "-i",
        "video.mp4",
        "-filter_complex",
        concat_filter(frame_counts=[53, 76]),
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "16",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "mezzanine.mp4",
    ]


def test_compose_filter_crops_exactly_then_scales_to_vertical() -> None:
    first = CropKeyframe(t_ms=0, x=820, y=0, w=608, h=1080)

    graph = compose_filter(first=first, commands_file="crop.cmd")

    assert graph == (
        "[0:v]sendcmd=f=crop.cmd,crop@camera=608:1080:820:0:exact=1,"
        "scale=1080:1920:flags=bicubic,setsar=1,format=yuv420p[v]"
    )


def test_build_compose_args_keeps_the_mezzanine_audio() -> None:
    first = CropKeyframe(t_ms=0, x=820, y=0, w=608, h=1080)

    args = build_compose_args("mezzanine.mp4", first, "crop.cmd", "clip.mp4")

    assert args[:3] == ["-y", "-i", "mezzanine.mp4"]
    assert args[args.index("-map") + 1 :][:3] == ["[v]", "-map", "0:a"]
    assert args[args.index("-c:a") + 1] == "copy"
    assert args[args.index("-r") + 1] == "30"
    assert args[-1] == "clip.mp4"


@pytest.mark.parametrize(
    ("first_line", "major", "supported"),
    [
        ("ffmpeg version 9.0.2-full_build-www.gyan.dev Copyright (c) 2000-2026", 9, True),
        ("ffmpeg version n9.0.2-963-g4d831360c9-20251125 Copyright (c) 2000-2026", 9, True),
        ("ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023 the FFmpeg developers", 6, False),
        ("ffmpeg version N-121234-gabcdef0123 Copyright (c) 2000-2026", None, True),
    ],
)
def test_ffmpeg_version_gate_for_the_variable_crop(
    first_line: str, major: int | None, supported: bool
) -> None:
    # Ubuntu 24.04's 6.1.1 crashes when crop changes size (CI, 26 nov 2026); a dev build
    # without a number cannot be judged, so it is let through.
    output = first_line + "\nbuilt with gcc 14\n"

    assert ffmpeg_major_version(output) == major
    assert ffmpeg_supports_variable_crop(output) is supported
