"""Check a camera path against the framing rules of docs/03 §5.3, for `verify-clip`.

Pure code: it reads the keyframes of `camera_path` and the main face boxes, and reports
where the face is cut too much, where the window jumps and where it wobbles. Positions
are mezzanine pixels (1920x1080 in the test recording), frames are mezzanine frames at
30 fps and times are clip milliseconds, as in `camera_path`.
"""

from pydantic import BaseModel, ConfigDict

from content_engine.piece_types.clip.domain.camera_path import (
    FACE_CROP_TOLERANCE,
    MAX_SPEED_PX_S,
    CropKeyframe,
    cut_frame_starts_ms,
    face_at,
)
from content_engine.piece_types.clip.domain.faces import FaceBox

ROUNDING_SLACK_PX = 1
"""Extra pixels of face that may be cut on each side, on top of what `camera_path` allows.

`camera_path` places the window with fractions of a pixel and then rounds it to whole
pixels (`_whole_start`), and `face_at` rounds the boxes it interpolates, so a window can
sit a fraction of a pixel past the exact limit. 1 px covers that rounding (approved by
Alex on 26 nov 2026 with the other `verify-clip` limits).
"""


class PathReport(BaseModel):
    """What `check_path` found on a camera path, for `verify_clip` to turn into checks.

    Attributes:
        frames: Number of keyframes, one per mezzanine frame.
        face_cut_frames: Frames where the window cuts more of the face, on some side,
            than `allowed_cut` permits, in frame order. Frames without a face box are
            not checked.
        worst_face_cut: Largest share of the face box left out on one side, over all
            frames and both axes: 0 when the face is always fully inside, 0.05 for 5 %.
        jumps: Frames, outside cuts, where the window center moved more than
            `MAX_SPEED_PX_S` / fps = 600 / 30 = 20 px since the previous frame on
            some axis, in frame order.
        largest_move_px: Largest move of the window center between two frames outside
            cuts, on one axis, in mezzanine pixels; a multiple of 0.5.
        wobbles: Frames where the window center goes a -> b -> a on some axis (the
            frame differs from the two around it, which are equal), in frame order.
            A cut on the frame or on the next one does not count.
    """

    frames: int
    face_cut_frames: list[int]
    worst_face_cut: float
    jumps: list[int]
    largest_move_px: float
    wobbles: list[int]

    model_config = ConfigDict(frozen=True)


def face_cut_share(
    start: int, size: int, face_start: int, face_size: int, frame_size: int
) -> float:
    """Return the share of the face box left out of the window on its worse side, on one axis.

    The face box is first clipped to the frame: boxes are not clipped when they are
    detected, so they can start below 0 or end past the frame edge (docs/03 §5.3,
    point 1), and the part of the face outside the video cannot be blamed on the
    window. Then it measures the visible face pixels before the window start and after
    the window end, and divides the larger of the two by the whole face size. The same
    function serves both axes: call it with x and widths, or with y and heights.

    Args:
        start: Left or top edge of the window, in mezzanine pixels.
        size: Width or height of the window, in pixels.
        face_start: Left or top edge of the face box, in mezzanine pixels. May be
            negative.
        face_size: Width or height of the face box, in pixels. More than 0.
        frame_size: Width or height of the mezzanine frame, in pixels.

    Returns:
        A share from 0 (the visible face is inside the window on this axis) to 1: 0.05
        means 5 % of the face is cut on one side.

    Example:
        Test stretch, frame 225: a 552 px window from x 922 to 1474 and a 615 px face
        from 891 to 1506. It loses 922 - 891 = 31 px on the left and 1506 - 1474 =
        32 px on the right: 32 / 615 = 5.2 %.

        >>> round(face_cut_share(922, 552, 891, 615, 1920), 3)
        0.052
        >>> face_cut_share(656, 608, 760, 400, 1920)
        0.0

        A 550 px face at x = -40 and a window at x = 0: the 40 px left of the frame are
        not in the video, so nothing is cut. Without clipping it would count
        40 / 550 = 7.3 %.

        >>> face_cut_share(0, 608, -40, 550, 1920)
        0.0
    """
    visible_start = max(face_start, 0)
    visible_end = min(face_start + face_size, frame_size)
    before = max(0, start - visible_start)
    after = max(0, visible_end - (start + size))
    return max(before, after) / face_size


def allowed_cut(size: int, face_size: int) -> float:
    """Return the largest share of the face box the window may leave out per side, on one axis.

    It mirrors `place_window` (`keep_face_visible`, docs/03 §5.3): up to
    `FACE_CROP_TOLERANCE` (5 %) of the face per side, or, when even the face core does
    not fit the window and `camera_path` centers the window on the face, half of the
    excess per side, (face_size - size) / 2, whichever is larger. `ROUNDING_SLACK_PX`
    (1 px) is added for rounding.

    Args:
        size: Width or height of the window, in pixels.
        face_size: Width or height of the face box, in pixels. More than 0.

    Returns:
        The allowed share of `face_size`, to compare with `face_cut_share`.

    Example:
        Test stretch, frame 225: a 615 px face in a 552 px window. 5 % is
        615 x 0.05 = 30.75 px, but centered the face loses (615 - 552) / 2 = 31.5 px
        per side, so the limit is 31.5 + 1 = 32.5 px, 32.5 / 615 = 5.3 %. A 400 px
        face in a 608 px window fits: 400 x 0.05 + 1 = 21 px, 21 / 400 = 5.25 %.

        >>> round(allowed_cut(size=552, face_size=615), 4)
        0.0528
        >>> allowed_cut(size=608, face_size=400)
        0.0525
    """
    allowed_px = max(FACE_CROP_TOLERANCE * face_size, (face_size - size) / 2)
    return (allowed_px + ROUNDING_SLACK_PX) / face_size


def _doubled_centers(keyframes: list[CropKeyframe]) -> tuple[list[int], list[int]]:
    """Return twice the window center on each axis, 2 x start + size, as whole numbers.

    Doubling keeps the center exact even when the size is odd, so two centers can be
    compared with `==`. A 552 px window at x 922 gives 2 x 922 + 552 = 2396, a center
    at 1198.

    Returns:
        The doubled x centers and the doubled y centers, one per keyframe.
    """
    xs = [2 * k.x + k.w for k in keyframes]
    ys = [2 * k.y + k.h for k in keyframes]
    return xs, ys


def check_path(
    keyframes: list[CropKeyframe],
    faces: list[FaceBox],
    cut_frames: list[int],
    frame_w: int,
    frame_h: int,
    fps: int = 30,
) -> PathReport:
    """Check that a camera path keeps the face in view and moves without jumps or wobbles.

    Three checks, each against the rules `camera_path` follows (docs/03 §5.3):

    1. Face inside: on each frame, the face box from `face_at` (with the cuts moved to
       the start of their frame by `cut_frame_starts_ms`, as `camera_path` does),
       clipped to the frame (`face_cut_share`), may be cut on each side by at most
       `allowed_cut`. Frames without a face box are skipped.
    2. Jumps: outside cuts, the window center may move at most `MAX_SPEED_PX_S` / fps
       = 600 / 30 = 20 px per frame on each axis. On a cut frame the camera jumps to
       the face on purpose, so it is not checked.
    3. Wobbles: the window center must not go a -> b -> a on consecutive frames, on
       either axis, unless a cut falls on the middle frame or the next one.

    Args:
        keyframes: One crop window per mezzanine frame, in frame order, from
            `camera_path`.
        faces: Boxes of the main face, in mezzanine pixels, sorted by `t_ms`.
        cut_frames: Frames where the image jumps to another shot, from
            `cut_at_frames`.
        frame_w: Width of the mezzanine frame, in pixels. `verify-clip` reads it from
            the mezzanine with `probe_video`.
        frame_h: Height of the mezzanine frame, in pixels, read the same way.
        fps: Frame rate of the mezzanine. 30 by default (docs/03 §5.2).

    Returns:
        A report with the frames that break each rule and the worst values found.

    Example:
        On the test stretch (words 29 to 108, 1004 frames, 9 cuts) nothing breaks:
        the worst face cut is 5.4 % (frame 321, within its limit) and the largest move
        17.0 px. Below, a 608 px window over a still 400 px face moves 1 px out and
        back at frame 2, a wobble, and 24 px at frame 4, more than 20 px: a jump,
        unless frame 4 is a cut.

        >>> faces = [
        ...     FaceBox(t_ms=t, x=760, y=300, w=400, h=400, score=0.9) for t in range(0, 1000, 100)
        ... ]
        >>> keyframes = [
        ...     CropKeyframe(t_ms=round(frame * 1000 / 30), x=x, y=0, w=608, h=1080)
        ...     for frame, x in enumerate([656, 656, 657, 656, 680])
        ... ]
        >>> report = check_path(keyframes, faces, cut_frames=[], frame_w=1920, frame_h=1080)
        >>> report.wobbles, report.jumps, report.largest_move_px
        ([2], [4], 24.0)
        >>> check_path(keyframes, faces, cut_frames=[4], frame_w=1920, frame_h=1080).jumps
        []
    """
    cuts = set(cut_frames)
    cut_frame_ms = cut_frame_starts_ms(sorted(cuts), fps)

    face_cut_frames: list[int] = []
    worst_face_cut = 0.0
    for frame, keyframe in enumerate(keyframes):
        face = face_at(faces, keyframe.t_ms, cut_frame_ms)
        if face is None:
            continue
        cut_x = face_cut_share(keyframe.x, keyframe.w, face.x, face.w, frame_w)
        cut_y = face_cut_share(keyframe.y, keyframe.h, face.y, face.h, frame_h)
        worst_face_cut = max(worst_face_cut, cut_x, cut_y)
        if cut_x > allowed_cut(keyframe.w, face.w) or cut_y > allowed_cut(keyframe.h, face.h):
            face_cut_frames.append(frame)

    xs, ys = _doubled_centers(keyframes)
    max_move = MAX_SPEED_PX_S / fps
    jumps: list[int] = []
    largest_move = 0.0
    for frame in range(1, len(keyframes)):
        if frame in cuts:
            continue
        move = max(abs(xs[frame] - xs[frame - 1]), abs(ys[frame] - ys[frame - 1])) / 2
        largest_move = max(largest_move, move)
        if move > max_move:
            jumps.append(frame)

    wobbles = [
        frame
        for frame in range(1, len(keyframes) - 1)
        if frame not in cuts
        and frame + 1 not in cuts
        and any(c[frame - 1] == c[frame + 1] != c[frame] for c in (xs, ys))
    ]

    return PathReport(
        frames=len(keyframes),
        face_cut_frames=face_cut_frames,
        worst_face_cut=worst_face_cut,
        jumps=jumps,
        largest_move_px=largest_move,
        wobbles=wobbles,
    )
