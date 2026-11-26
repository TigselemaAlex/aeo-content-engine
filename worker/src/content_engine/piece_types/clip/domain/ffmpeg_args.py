"""Build the FFmpeg arguments that cut the mezzanine and compose the vertical clip.

Two commands: one cuts a timeline into the mezzanine (docs/03 §5.2), the other crops
the mezzanine along the camera path and scales it to the 1080x1920 clip (docs/03 §5.6).
Pure code: it only builds lists of strings; the media adapter runs FFmpeg. Cut times
are milliseconds of the original video and FFmpeg receives them in seconds. Frame
counts are frames of the mezzanine, which runs at a constant 30 fps, and crop windows
are mezzanine pixels.
"""

from content_engine.piece_types.clip.domain.camera_path import CropKeyframe
from content_engine.piece_types.clip.domain.sendcmd import CROP_FILTER
from content_engine.piece_types.clip.domain.timeline import Cut, Timeline

VIDEO_READ_EXTRA_MS = 100
"""Extra milliseconds read for each image cut, beyond its length (docs/03 §5.2).

They make sure there are always frames to trim. With the rounding on the running total
(`frame_counts`) a cut may need up to 1 frame more than its own length, 1000 / 30 =
33.3 ms, and with a 24 fps original the read may fall short by a whole source frame,
1000 / 24 = 41.7 ms. The worst case is 33.3 + 41.7 = 75 ms, which 100 ms covers with
room to spare. Checked on the test recording: a 1035 ms cut that must get 32 frames
comes out with 31 without the extra read, and with 32 with 100 ms (decision
"Extracción del intermedio", docs/00).

`concat_filter` then trims every image cut to its exact frame count, so the extra
frames are dropped and never reach the mezzanine.
"""


def seconds(ms: int) -> str:
    """Format milliseconds as the seconds string FFmpeg takes in `-ss` and `-t`.

    The count is ms / 1000 -> s, written with 3 decimals so no millisecond is lost.

    Args:
        ms: A time or a duration in milliseconds.

    Returns:
        The seconds as text, such as `"2.940"`.

    Example:
        2940 / 1000 = 2.940 s.

        >>> seconds(2940)
        '2.940'
        >>> seconds(61234)
        '61.234'
    """
    return f"{ms / 1000:.3f}"


def input_args(source: str, cut: Cut, extra_ms: int = 0) -> list[str]:
    """Build the FFmpeg input that reads one cut of the source video.

    `-ss` before `-i` seeks straight to the cut's start, so FFmpeg does not decode
    the video from the beginning, and `-t` reads only the cut's length (docs/03 §5.2).

    Args:
        source: Path or URL of the original video.
        cut: The range to read, in milliseconds of the original video.
        extra_ms: Milliseconds to read past the cut's end. 0 or more;
            `build_extract_args` passes `VIDEO_READ_EXTRA_MS` for image cuts.

    Returns:
        The six arguments `-ss <start> -t <duration> -i <source>`, times in seconds.

    Example:
        The cut 2940-5620 ms starts at 2.940 s and lasts 5620 - 2940 = 2680 ms, or
        2.780 s with 100 ms extra.

        >>> input_args("video.mp4", Cut(start_ms=2940, end_ms=5620))
        ['-ss', '2.940', '-t', '2.680', '-i', 'video.mp4']
        >>> input_args("video.mp4", Cut(start_ms=2940, end_ms=5620), extra_ms=100)[3]
        '2.780'
    """
    duration_ms = cut.end_ms - cut.start_ms + extra_ms
    return ["-ss", seconds(cut.start_ms), "-t", seconds(duration_ms), "-i", source]


def frame_counts(cuts: list[Cut], fps: int = 30) -> list[int]:
    """Return the frames each cut gets in the clip, rounded on the running total.

    Rounding where each cut ends in the clip, instead of each cut on its own,
    keeps every cut within half a frame of its place: the errors never add up.
    Cut k ends at frame round(end of cut k in the clip in ms x fps / 1000), and gets
    that frame minus where the previous cut ended (docs/03 §5.2). The camera path
    uses the same count to place its frames (docs/03 §5.3).

    Args:
        cuts: Cuts in play order. Only their lengths matter, not where they start.
        fps: Frames per second of the mezzanine. 30 by default (docs/03 §5.2).

    Returns:
        One frame count per cut, each 1 or more. They add up to the clip's length in
        frames. Empty if `cuts` is empty.

    Raises:
        ValueError: If a cut gets no frame after rounding. Only a cut shorter than one
            frame (1000 / 30 = 33.3 ms at 30 fps) can.

    Example:
        Image cuts of 3206, 2350 and 1131 ms from the test recording end at 3206, 5556
        and 6687 ms in the clip. In frames, ms x 30 / 1000 gives 96.18, 166.68 and
        200.61, rounded to 96, 167 and 201, so the cuts get 96, 167 - 96 = 71 and
        201 - 167 = 34 frames.

        >>> frame_counts([
        ...     Cut(start_ms=0, end_ms=3206),
        ...     Cut(start_ms=0, end_ms=2350),
        ...     Cut(start_ms=0, end_ms=1131),
        ... ])
        [96, 71, 34]
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
    silence or frozen frames are added (docs/03 §5.2).

    Each video cut resets its timestamps to 0 (`setpts=PTS-STARTPTS`), is converted
    to `fps`, keeps only its first frames (`trim=end_frame`) and resets its timestamps
    again before the join.

    Args:
        frame_counts: Frames of each cut, in play order, as returned by the function
            `frame_counts`.
        fps: Frames per second of the mezzanine. 30 by default (docs/03 §5.2).

    Returns:
        A `-filter_complex` graph whose outputs are `[v]` (video) and `[a]` (audio).

    Example:
        Two cuts of 53 and 76 frames: inputs 0 and 2 are their images, 1 and 3 their
        audio.

        >>> for part in concat_filter([53, 76]).split(";"):
        ...     print(part)
        [0:v]setpts=PTS-STARTPTS,fps=30,trim=end_frame=53,setpts=PTS-STARTPTS[v0]
        [2:v]setpts=PTS-STARTPTS,fps=30,trim=end_frame=76,setpts=PTS-STARTPTS[v1]
        [v0][v1]concat=n=2:v=1:a=0[v]
        [1:a][3:a]concat=n=2:v=0:a=1[a]
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
    """Build the FFmpeg arguments that cut a timeline into the mezzanine.

    Each cut becomes two inputs, its image (`timeline.video_cuts`, read
    `VIDEO_READ_EXTRA_MS` longer) and its audio (`timeline.cuts`). `concat_filter`
    trims each image to its frame count and joins images and audio separately. The
    output follows docs/03 §5.2: H.264 (`libx264`) with CRF 16, preset `veryfast`
    and `yuv420p`, plus AAC audio at 192 kbps and 48 kHz. `veryfast` because the
    mezzanine is temporary and speed matters more than size (decision "Extracción del
    intermedio", docs/00). `-y` overwrites `output` if it exists.

    Args:
        source: Path or URL of the original video.
        timeline: The clip's audio and image cuts.
        output: Path of the mezzanine to write.
        fps: Frame rate of the mezzanine. 30 by default (docs/03 §5.2).

    Returns:
        The arguments to pass after the `ffmpeg` program name.

    Raises:
        ValueError: From `frame_counts`, if an image cut is shorter than one frame.

    Example:
        Image cuts of 1753 and 2547 ms are read as 1753 + 100 = 1853 ms and
        2547 + 100 = 2647 ms. They are trimmed to 1753 x 30 / 1000 = 52.59 -> 53 frames
        and 4300 x 30 / 1000 = 129 -> 129 - 53 = 76 frames.

        >>> timeline = Timeline(
        ...     cuts=[Cut(start_ms=0, end_ms=1620), Cut(start_ms=2940, end_ms=5620)],
        ...     video_cuts=[Cut(start_ms=0, end_ms=1753), Cut(start_ms=3073, end_ms=5620)],
        ... )
        >>> args = build_extract_args("video.mp4", timeline, "mezzanine.mp4")
        >>> args[1:7]
        ['-ss', '0.000', '-t', '1.853', '-i', 'video.mp4']
        >>> args[13:19]
        ['-ss', '3.073', '-t', '2.647', '-i', 'video.mp4']
        >>> "trim=end_frame=53" in args[26] and "trim=end_frame=76" in args[26]
        True
    """
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


OUTPUT_W, OUTPUT_H = 1080, 1920
"""Width and height of the vertical clip, in pixels: 9:16 (docs/03 §5.3 and §5.6)."""

COMPOSE_CRF = 18
"""H.264 quality of the vertical clip (`-crf`): the lower, the better and the larger.

Provisional: picked by the developer, not measured; T2.7 measures the time per clip.
The mezzanine uses CRF 16 (docs/03 §5.2).
"""

COMPOSE_PRESET = "veryfast"
"""x264 speed preset of the vertical clip (`-preset`): faster ones encode quicker, larger.

Provisional: picked by the developer, not measured; T2.7 measures the time per clip. The
mezzanine uses `veryfast` too (docs/03 §5.2).
"""

SCALE_FLAGS = "bicubic"
"""Scaler FFmpeg uses to enlarge each crop window to 1080x1920.

Chosen by Alex on 26 nov 2026 from a comparison on the test stretch (33.5 s): encode
time, and detail kept, measured by shrinking the output back and comparing it with the
source crop. bilinear 6.0 s and 43.8 dB, bicubic 6.7 s and 45.4 dB, lanczos 8.1 s and
44.5 dB, spline 17.3 s and 44.4 dB. bicubic and lanczos look the same on the face, and
bicubic keeps the most detail for less time.
"""


def compose_filter(first: CropKeyframe, commands_file: str) -> str:
    """Build the `-filter_complex` graph that crops along the camera path and scales to 9:16.

    Four filters on the mezzanine video, in order:

    1. `sendcmd` reads the script of `crop_commands` and moves the crop window on
       every frame where it changes.
    2. `crop@camera` (`CROP_FILTER`) starts with the window of the first frame. It
       needs `exact=1`: without it, crop rounds odd x and y down to even on yuv420p
       video (its color is stored at half resolution), so the camera moved in 2 px
       steps. Measured on the test stretch (1004 frames): without `exact=1`, 53
       frames matched a neighbour's window better than their own; with it, 0.
    3. `scale` enlarges each window to `OUTPUT_W` x `OUTPUT_H` with `SCALE_FLAGS`.
       The crop size changes during the clip with the zooms and cut bridges (92
       sizes and 208 size changes on the test stretch); scale adapts to each new
       input size, so the output always stays 1080x1920. `setsar=1` keeps pixels
       square: a 552x982 window is not exactly 9:16, and scale would otherwise mark
       the output with a non-square pixel shape to keep the window's proportions.
    4. `format=yuv420p`, the pixel format of the clip (docs/03 §5.6).

    Args:
        first: Crop window of frame 0, from `camera_path`.
        commands_file: Path of the `sendcmd` script, as FFmpeg reads it. `compose_clip`
            passes a bare file name, because a Windows path such as `C:/...` breaks
            the filter on its `:`.

    Returns:
        The graph, with the mezzanine as input `[0:v]` and the clip video as `[v]`.

    Example:
        The test stretch starts with the 608x1080 window at x 820:

        >>> first = CropKeyframe(t_ms=0, x=820, y=0, w=608, h=1080)
        >>> for part in compose_filter(first, "crop.cmd").split(","):
        ...     print(part)
        [0:v]sendcmd=f=crop.cmd
        crop@camera=608:1080:820:0:exact=1
        scale=1080:1920:flags=bicubic
        setsar=1
        format=yuv420p[v]
    """
    return (
        f"[0:v]sendcmd=f={commands_file},"
        f"{CROP_FILTER}={first.w}:{first.h}:{first.x}:{first.y}:exact=1,"
        f"scale={OUTPUT_W}:{OUTPUT_H}:flags={SCALE_FLAGS},setsar=1,format=yuv420p[v]"
    )


def build_compose_args(
    mezzanine: str, first: CropKeyframe, commands_file: str, output: str, fps: int = 30
) -> list[str]:
    """Build the FFmpeg arguments that turn the mezzanine into the vertical clip.

    The video goes through `compose_filter` and is encoded as H.264 High in yuv420p at
    `fps`, with `+faststart` so it can start playing before it is fully downloaded
    (docs/03 §5.6), with `COMPOSE_PRESET` and `COMPOSE_CRF`. The audio is copied from
    the mezzanine (AAC 48 kHz, docs/03 §5.2) without re-encoding; normalizing its
    loudness comes in T2.5. `-y` overwrites `output` if it exists.

    Args:
        mezzanine: Path of the mezzanine, from `extract_clip`.
        first: Crop window of frame 0, from `camera_path`.
        commands_file: Path of the `sendcmd` script, as FFmpeg reads it (see
            `compose_filter`).
        output: Path of the clip to write.
        fps: Frame rate of the clip. 30 by default (docs/03 §5.6).

    Returns:
        The arguments to pass after the `ffmpeg` program name.

    Example:
        >>> first = CropKeyframe(t_ms=0, x=820, y=0, w=608, h=1080)
        >>> args = build_compose_args("mezzanine.mp4", first, "crop.cmd", "clip.mp4")
        >>> args[:3], args[5:9]
        (['-y', '-i', 'mezzanine.mp4'], ['-map', '[v]', '-map', '0:a'])
        >>> args[9:17]
        ['-c:v', 'libx264', '-profile:v', 'high', '-preset', 'veryfast', '-crf', '18']
        >>> args[17:]
        ['-r', '30', '-c:a', 'copy', '-movflags', '+faststart', 'clip.mp4']
    """
    return [
        "-y",
        "-i",
        mezzanine,
        "-filter_complex",
        compose_filter(first=first, commands_file=commands_file),
        "-map",
        "[v]",
        "-map",
        "0:a",
        "-c:v",
        "libx264",
        "-profile:v",
        "high",
        "-preset",
        COMPOSE_PRESET,
        "-crf",
        str(COMPOSE_CRF),
        "-r",
        str(fps),
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        output,
    ]
