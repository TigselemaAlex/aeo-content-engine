from content_engine.piece_types.clip.domain.ffmpeg_args import (
    build_extract_args,
    concat_filter,
    input_args,
    seconds,
)
from content_engine.piece_types.clip.domain.timeline import Cut, Timeline


def test_seconds_fromats_ms_with_three_decimals() -> None:
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


def test_concat_filter_pairs_video_and_audio_of_each_cut() -> None:
    assert concat_filter(cut_count=2) == (
        "[0:v][1:a][2:v][3:a]concat=n=2:v=1:a=1[joined][a];[joined]fps=30[v]"
    )


def test_concat_filter_with_one_cut() -> None:
    assert concat_filter(cut_count=1) == (
        "[0:v][1:a]concat=n=1:v=1:a=1[joined][a];[joined]fps=30[v]"
    )


def test_build_extract_Args_cuts_video_and_audio_and_joins_them() -> None:
    timeline = Timeline(
        cuts=[Cut(start_ms=0, end_ms=1620), Cut(start_ms=2940, end_ms=5620)],
        video_cuts=[Cut(start_ms=0, end_ms=1753), Cut(start_ms=3073, end_ms=5620)],
    )

    args = build_extract_args(source="video.mp4", timeline=timeline, output="mezzanine.mp4")

    assert args == [
        "-y",
        "-ss",
        "0.000",
        "-t",
        "1.753",
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
        "2.547",
        "-i",
        "video.mp4",
        "-ss",
        "2.940",
        "-t",
        "2.680",
        "-i",
        "video.mp4",
        "-filter_complex",
        "[0:v][1:a][2:v][3:a]concat=n=2:v=1:a=1[joined][a];[joined]fps=30[v]",
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
