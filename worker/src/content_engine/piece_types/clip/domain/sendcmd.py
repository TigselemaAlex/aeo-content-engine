"""Build the FFmpeg `sendcmd` script that moves the crop window frame by frame (docs/03 §5.6).

Pure code: it only builds text; the media adapter writes it to a file and runs FFmpeg.
Times are seconds of the mezzanine, frame / 30, and window positions and sizes are
mezzanine pixels (1920x1080 in the test recording), as in `CropKeyframe`.
"""

from content_engine.piece_types.clip.domain.camera_path import CropKeyframe

CROP_FILTER = "crop@camera"
"""Name of the crop filter the commands are sent to: FFmpeg's `crop` with the label `camera`.

`compose_filter` creates the filter under this name, so a command such as
`[enter] crop@camera x 946` reaches it.
"""

_PARAMS = ("w", "h", "x", "y")
"""The crop values a command can set, in the order they are written on each line."""


def command_time_s(frame: int, fps: int = 30) -> float:
    """Return the time, in seconds of the mezzanine, at which to send the commands of a frame.

    `sendcmd` applies a command at time t to the first frame whose timestamp is t or
    later. Frame n starts at n / fps s, so the command goes half a frame earlier,
    (n - 0.5) / fps: always after frame n - 1 starts and never after frame n does,
    so it lands on frame n. Frame 0 gets 0, the start of the video.

    The keyframe's own `t_ms` does not work: it is rounded to whole milliseconds and
    may fall after its frame starts. Frame 2 starts at 2 / 30 = 0.0667 s but has
    `t_ms` 67, so a command at 0.067 s lands on frame 3. Measured on the test stretch
    (words 29 to 108, 1004 frames): 334 frames have a `t_ms` later than their start,
    and with `t_ms` as the time 188 output frames matched a neighbour's window better
    than their own, among them the cut frames 167, 380 and 803.

    Args:
        frame: Index of the mezzanine frame, 0 or more.
        fps: Frame rate of the mezzanine. 30 by default (docs/03 §5.2).

    Returns:
        The time in seconds.

    Example:
        Frame 2: (2 - 0.5) / 30 = 0.05 s, between the start of frame 1 (0.0333 s) and
        of frame 2 (0.0667 s). Frame 96, the first cut bridge of the test stretch:
        (96 - 0.5) / 30 = 3.1833 s.

        >>> command_time_s(0)
        0.0
        >>> command_time_s(2)
        0.05
        >>> round(command_time_s(96), 4)
        3.1833
    """
    if frame == 0:
        return 0.0
    return (frame - 0.5) / fps


def crop_commands(keyframes: list[CropKeyframe], fps: int = 30) -> str:
    """Build the `sendcmd` script that gives every frame its crop window.

    The list index is the frame number. Each frame whose window differs from the
    previous one gets a line at `command_time_s(frame)` with one `[enter]` command per
    value that changed, in the order w, h, x, y; the first frame sets all four. A frame
    with the same window as the previous one gets no line. Times are written with 4
    decimals. Writing only the changes keeps the script short: 579 lines for the 1004
    frames of the test stretch.

    Args:
        keyframes: One crop window per mezzanine frame, in frame order, as
            `camera_path` returns them. Their `t_ms` is not used.
        fps: Frame rate of the mezzanine. 30 by default (docs/03 §5.2).

    Returns:
        The script, one line per changed frame, each ending in `;` and a newline.
        An empty string if `keyframes` is empty.

    Example:
        On the test stretch the first cut bridge, at frame 96, switches from the
        608x1080 window to a 552x982 one, so all four values change in one line:
        `3.1833 [enter] crop@camera w 552, [enter] crop@camera h 982,
        [enter] crop@camera x 946, [enter] crop@camera y 23;`. Below, frame 1 repeats
        frame 0 and gets no line, and frame 2 only moves x:

        >>> keyframes = [
        ...     CropKeyframe(t_ms=0, x=820, y=0, w=608, h=1080),
        ...     CropKeyframe(t_ms=33, x=820, y=0, w=608, h=1080),
        ...     CropKeyframe(t_ms=67, x=822, y=0, w=608, h=1080),
        ... ]
        >>> lines = crop_commands(keyframes).splitlines()
        >>> for command in lines[0].split(", "):
        ...     print(command)
        0.0000 [enter] crop@camera w 608
        [enter] crop@camera h 1080
        [enter] crop@camera x 820
        [enter] crop@camera y 0;
        >>> lines[1]
        '0.0500 [enter] crop@camera x 822;'
    """
    lines: list[str] = []
    previous: CropKeyframe | None = None
    for frame, keyframe in enumerate(keyframes):
        changed = [
            param
            for param in _PARAMS
            if previous is None or getattr(previous, param) != getattr(keyframe, param)
        ]
        if changed:
            commands = ", ".join(
                f"[enter] {CROP_FILTER} {param} {getattr(keyframe, param)}" for param in changed
            )
            lines.append(f"{command_time_s(frame, fps):.4f} {commands};")
        previous = keyframe
    return "\n".join(lines) + "\n" if lines else ""
