from content_engine.piece_types.clip.domain.timeline import Cut, Timeline


def seconds(ms: int) -> str:
    return f"{ms / 1000:.3f}"


def input_args(source: str, cut: Cut) -> list[str]:
    return ["-ss", seconds(cut.start_ms), "-t", seconds(cut.end_ms - cut.start_ms), "-i", source]


def concat_filter(cut_count: int, fps: int = 30) -> str:
    labels = "".join(f"[{2 * k}:v][{2 * k + 1}:a]" for k in range(cut_count))
    return f"{labels}concat=n={cut_count}:v=1:a=1[joined][a];[joined]fps={fps}[v]"


def build_extract_args(source: str, timeline: Timeline, output: str, fps: int = 30) -> list[str]:
    args = ["-y"]

    for video_cut, audio_cut in zip(timeline.video_cuts, timeline.cuts, strict=True):
        args.extend(input_args(source=source, cut=video_cut))
        args.extend(input_args(source=source, cut=audio_cut))

    args.extend(
        [
            "-filter_complex",
            concat_filter(cut_count=len(timeline.cuts), fps=fps),
            "-map",
            "[v]",
            "-map",
            "[a]",
        ]
    )

    args.extend(
        [
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
            output,
        ]
    )

    return args
