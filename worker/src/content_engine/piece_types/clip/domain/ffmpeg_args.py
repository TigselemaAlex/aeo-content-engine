from content_engine.piece_types.clip.domain.timeline import Cut, Timeline

VIDEO_READ_EXTRA_MS = 100


def seconds(ms: int) -> str:
    return f"{ms / 1000:.3f}"


def input_args(source: str, cut: Cut, extra_ms: int = 0) -> list[str]:
    duration_ms = cut.end_ms - cut.start_ms + extra_ms
    return ["-ss", seconds(cut.start_ms), "-t", seconds(duration_ms), "-i", source]


def frame_counts(cuts: list[Cut], fps: int = 30) -> list[int]:
    """Frames each cut gets in the clip, rounded on the running total.

    Rounding where each cut ends in the clip, instead of each cut on its own,
    keeps every cut within half a frame of its place: the errors never add up.
    """
    counts: list[int] = []
    elapsed_ms = 0
    first_frame = 0
    for k, cut in enumerate(cuts):
        elapsed_ms += cut.end_ms - cut.start_ms
        last_frame = round(elapsed_ms * fps / 1000)
        if last_frame == first_frame:
            raise ValueError(f"cut {k} lasts {cut.end_ms - cut.start_ms} ms, less than one frame")
        counts.append(last_frame - first_frame)
        first_frame = last_frame
    return counts


def concat_filter(frame_counts: list[int], fps: int = 30) -> str:
    """Join the video cuts and the audio cuts as two separate tracks.

    Inputs come in pairs: 2k is the video of cut k and 2k + 1 its audio.
    Each video cut is set to fps and trimmed to its exact frame count. Video
    and audio are joined on their own, so J cuts keep their offset and no
    silence or frozen frames are added.
    """
    cut_count = len(frame_counts)
    video_parts = [
        f"[{2 * k}:v]setpts=PTS-STARTPTS,fps={fps},trim=end_frame={count},setpts=PTS-STARTPTS[v{k}]"
        for k, count in enumerate(frame_counts)
    ]
    video_labels = "".join(f"[v{k}]" for k in range(cut_count))
    audio_labels = "".join(f"[{2 * k + 1}:a]" for k in range(cut_count))
    return ";".join(
        [
            *video_parts,
            f"{video_labels}concat=n={cut_count}:v=1:a=0[v]",
            f"{audio_labels}concat=n={cut_count}:v=0:a=1[a]",
        ]
    )


def build_extract_args(source: str, timeline: Timeline, output: str, fps: int = 30) -> list[str]:
    args = ["-y"]

    for video_cut, audio_cut in zip(timeline.video_cuts, timeline.cuts, strict=True):
        args.extend(input_args(source=source, cut=video_cut, extra_ms=VIDEO_READ_EXTRA_MS))
        args.extend(input_args(source=source, cut=audio_cut))

    args.extend(
        [
            "-filter_complex",
            concat_filter(frame_counts=frame_counts(cuts=timeline.video_cuts, fps=fps), fps=fps),
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
