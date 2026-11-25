"""Camera path: where the vertical 9:16 window sits on every frame of the mezzanine.

The path follows the main face with a dead zone and a spring, keeps the face
visible, adds the zooms and cut bridges, and reports the stretches without a
face (docs/03 §5.3).

All positions are in mezzanine pixels (the original resolution, 1920x1080 in
the test recording) and all times in clip milliseconds: from the start of the
mezzanine, the same clock as `FaceBox.t_ms` and `Timeline.video_cut_points_ms`.
"""

from bisect import bisect_right
from dataclasses import dataclass
from itertools import pairwise

from pydantic import BaseModel, ConfigDict, Field

from content_engine.piece_types.clip.domain.faces import FaceBox

DEAD_ZONE_RATIO = 0.10
"""Central part of the window where face moves do not move the camera, as a share of its side.

10 % of the window side on each axis (docs/03 §5.3): the width on the horizontal
axis, 608 x 0.10 / 2 = 30.4 px to each side of the center on a 608 px window, and
the height on the vertical axis, 982 x 0.10 / 2 = 49.1 px on the 982 px window of
a cut bridge. Without zoom the window takes the full frame height and does not
move vertically. Tuned on the test recording (decision "Camino de cámara",
docs/00): the face (549 px) nearly fills the window (608 px), so about 30 px of
dead zone matches the free margin around it. Vertically there is more room to
spare: with 10 % of the height the window moves vertically on 181 frames of the
test clip (words 29 to 108, 1004 frames), against 299 with 10 % of the width.
"""

SPRING_OMEGA = 8.0
"""Stiffness of the critically damped spring that smooths the camera, per second.

With omega = 8 the window reaches the face in about 0.6 s without
overshooting (docs/03 §5.3, docs/00).
"""

MAX_SPEED_PX_S = 600.0
"""Top speed of the window center, in mezzanine pixels per second.

600 px/s / 30 fps = 20 px per frame (docs/03 §5.3). Keeping the face visible
wins over it: `camera_path` pushes the window along with a fast face.
"""

FACE_CROP_TOLERANCE = 0.05
"""Fraction of the face box that may stay out of the window on each side.

On the 549 px face of the test recording, 549 x 0.05 = 27.45 px per side
(docs/03 §5.3). Tuned on the test clip (words 29 to 108, 33.5 s), without zooms
or bridges: the detected box width moved between 522 and 615 px; without
tolerance the window copied that noise and changed direction 73 times, with 5 %
only 24 (decision "Camino de cámara", docs/00).
"""

BRIDGE_SCALE = 1.10
"""Framing scale of a cut bridge: each video cut switches between 100 % and 110 %.

The cut reads as a change of shot instead of a jump (docs/03 §5.3). On a
1920x1080 frame the window goes from 608x1080 to 552x982.
"""

ZOOM_HOLD_MS = 1000
"""How long a zoom stays at full scale, in milliseconds.

A zoom is 1.5 s in + 1 s held + 1.5 s out = 4 s, the minimum gap between
zooms (docs/03 §5.3).
"""

FACE_GAP_MS = 200
"""Longest time between two face boxes that is still interpolated, in milliseconds.

Boxes come every ~100 ms; a gap is more than 200 ms between two boxes, and
across a gap the last box is held (docs/03 §5.3).
"""

NO_FACE_MIN_MS = 2000
"""Shortest stretch with no face box reported in `CameraPath.no_face`, in milliseconds.

The render shows stretches longer than 2 s with `fit_blur` (docs/03 §5.3).
"""


class CropKeyframe(BaseModel):
    """The crop window on one frame of the mezzanine. (x, y) is the top-left corner.

    Attributes:
        t_ms: Start of the frame, in clip milliseconds: round(frame x 1000 / 30),
            so 0, 33, 67... 0 or more.
        x: Left edge of the window, in mezzanine pixels. 0 or more.
        y: Top edge of the window, in mezzanine pixels. 0 or more.
        w: Width of the window, in mezzanine pixels. More than 0; `camera_path`
            always makes it even.
        h: Height of the window, in mezzanine pixels. More than 0; `camera_path`
            always makes it even.
    """

    t_ms: int = Field(ge=0)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)

    model_config = ConfigDict(frozen=True)


class NoFaceRange(BaseModel):
    """A stretch of the clip with no face box for longer than `NO_FACE_MIN_MS` (2 s).

    The render shows it with `fit_blur` instead of the face crop (docs/03 §5.3).

    Attributes:
        start_ms: Time of the last face box before the stretch, or 0 if the clip
            starts without a face, in clip milliseconds. 0 or more.
        end_ms: Time of the next face box, or the clip duration if no face comes
            back, in clip milliseconds. 0 or more.
    """

    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)

    model_config = ConfigDict(frozen=True)


class CameraPath(BaseModel):
    """The crop window for a whole clip, built by `camera_path`.

    Attributes:
        keyframes: One crop window per frame of the mezzanine, in frame order:
            round(duration_ms x 30 / 1000) of them (docs/03 §5.3).
        no_face: Stretches longer than 2 s with no face box, in time order, for
            the render to use `fit_blur` (docs/03 §5.3). Empty if the face never
            leaves for that long.
    """

    keyframes: list[CropKeyframe]
    no_face: list[NoFaceRange]

    model_config = ConfigDict(frozen=True)


def _even(value: float) -> int:
    """Round to the nearest even integer, as yuv420p video sizes need (docs/03 §5.3).

    Uses Python's round(), which breaks a tie toward the even number
    ("banker's rounding"): 405 / 2 = 202.5 -> round(202.5) = 202 -> 404, but
    407 / 2 = 203.5 -> round(203.5) = 204 -> 408. A 1280x720 video gives
    720 x 9 / 16 = 405, so its window is 404 px wide.

    >>> _even(405)
    404
    >>> _even(407)
    408
    >>> _even(607.5)
    608
    """
    return 2 * round(value / 2)


def crop_window_size(frame_w: int, frame_h: int, scale: float = 1.0) -> tuple[int, int]:
    """Return the width and height of the 9:16 crop window for a frame.

    The window takes the full frame height and a width of height x 9 / 16,
    the shape of the vertical output video (1080x1920, docs/03 §5.3).
    A scale above 1 shrinks both sides by that factor, to zoom in.
    Both sides are rounded to the nearest even number because yuv420p
    video stores color at half resolution and needs even sizes (docs/03 §5.3).

    Args:
        frame_w: Width of the mezzanine frame, in pixels.
        frame_h: Height of the mezzanine frame, in pixels.
        scale: Zoom factor. 1.0 is no zoom, 1.10 a cut bridge and 1.15 a full
            zoom (Edit Spec `zoom.max_scale`, docs/03 §5.3).

    Returns:
        A `(width, height)` tuple in pixels, both even.

    Raises:
        ValueError: If `scale` is below 1, or if the frame is narrower than
            9:16 (for example, a 1080x2340 phone screen recording).

    Example:
        1080 x 9 / 16 = 607.5, rounded to the even 608. With scale 1.15:
        607.5 / 1.15 = 528.3 -> 528, and 1080 / 1.15 = 939.1 -> 940.

        >>> crop_window_size(1920, 1080)
        (608, 1080)
        >>> crop_window_size(1920, 1080, scale=1.15)
        (528, 940)
    """
    if scale < 1:
        raise ValueError("scale must be 1 or more")
    w = _even(frame_h * 9 / 16 / scale)
    h = _even(frame_h / scale)
    if w > frame_w:
        raise ValueError(f"a {frame_w}x{frame_h} frame is too narrow for a 9:16 window")
    return w, h


def place_window(
    center: float, size: int, face_start: float, face_size: float, frame_size: int
) -> float:
    """Return the start (left or top edge) of the window on one axis.

    This is `keep_face_visible` (docs/03 §5.3). The window is centered on
    `center`, then moved just enough to keep the face inside it. Up to
    `FACE_CROP_TOLERANCE` (5 %) of the face may be left out on each side, so
    the noisy edges of the detected box do not shake the window. If even that
    face core is bigger than the window, the window is centered on the face so
    both sides lose the same amount. Last, the window is kept inside the frame.
    The same function serves both axes: call it with x and widths, or with y
    and heights.

    Args:
        center: Where the camera wants the window center, in mezzanine pixels.
        size: Window size on this axis, in pixels (from `crop_window_size`).
        face_start: Left or top edge of the face box, in mezzanine pixels.
        face_size: Width or height of the face box, in pixels.
        frame_size: Width or height of the mezzanine frame, in pixels.

    Returns:
        The window start in mezzanine pixels, between 0 and
        `frame_size - size`. Not rounded.

    Example:
        Test recording: 608 px window, 549 px face from 1000 to 1549, camera
        at 960. The tolerance is 549 x 0.05 = 27.45 px per side, so the face
        core runs from 1027.45 to 1521.55. Centered, the window would start at
        960 - 304 = 656 and cut the core; it must start at 1521.55 - 608 =
        913.55 or later, and it moves just that far.

        >>> round(place_window(960, 608, 1000, 549, 1920), 2)
        913.55

        A 600 px face has a 540 px core, more than a 528 px zoomed window:
        the window centers on the face, 849 + 300 - 264 = 885.

        >>> place_window(960, 528, 849, 600, 1920)
        885.0
    """
    margin = face_size * FACE_CROP_TOLERANCE
    face_start += margin
    face_size -= 2 * margin

    start = center - size / 2
    if face_size <= size:
        start = min(max(start, face_start + face_size - size), face_start)
    else:
        start = face_start + face_size / 2 - size / 2
    return min(max(start, 0), frame_size - size)


def face_at(faces: list[FaceBox], t_ms: int, cut_at_ms: list[int] | None = None) -> FaceBox | None:
    """Return the face box at any moment, from boxes sampled every ~100 ms.

    Between two close boxes the position is interpolated in a straight line,
    except across a cut: the two boxes belong to different shots, so the box
    on the same side of the cut as `t_ms` is used. Across a gap longer than
    `FACE_GAP_MS` (200 ms) the last box is held; before the first box, the
    first box is used, and after the last box, the last one (docs/03 §5.3).

    Args:
        faces: Boxes of the main face, sorted by `t_ms`.
        t_ms: The moment to look at, in clip milliseconds.
        cut_at_ms: Clip times where the image jumps to another shot. A cut at
            `t_ms` counts as already happened. None means no cuts.

    Returns:
        An interpolated box stamped with `t_ms` and the lower of the two scores,
        or one of the original boxes unchanged (with its own `t_ms`) when it is
        held, used across a cut or `t_ms` falls outside the boxes. None if
        `faces` is empty.

    Example:
        Boxes at 0 ms (x = 100) and 100 ms (x = 200): at 50 ms the face is
        halfway, x = 100 + (200 - 100) x 50 / 100 = 150. With a cut at 67 ms,
        50 ms keeps the box before the cut.

        >>> faces = [
        ...     FaceBox(t_ms=0, x=100, y=490, w=100, h=100, score=0.9),
        ...     FaceBox(t_ms=100, x=200, y=490, w=100, h=100, score=0.8),
        ... ]
        >>> face_at(faces, 50)
        FaceBox(t_ms=50, x=150, y=490, w=100, h=100, score=0.8)
        >>> face_at(faces, 50, cut_at_ms=[67])
        FaceBox(t_ms=0, x=100, y=490, w=100, h=100, score=0.9)
    """
    if not faces:
        return None
    times = [box.t_ms for box in faces]
    after_index = bisect_right(times, t_ms)
    if after_index == 0:
        return faces[0]
    before = faces[after_index - 1]
    if after_index == len(faces):
        return before
    after = faces[after_index]
    cut = next((ms for ms in cut_at_ms or [] if before.t_ms < ms <= after.t_ms), None)
    if cut is not None:
        return after if t_ms >= cut else before
    if after.t_ms - before.t_ms > FACE_GAP_MS:
        return before

    progress = (t_ms - before.t_ms) / (after.t_ms - before.t_ms)

    def mix(a: int, b: int) -> int:
        return round(a + (b - a) * progress)

    return FaceBox(
        t_ms=t_ms,
        x=mix(before.x, after.x),
        y=mix(before.y, after.y),
        w=mix(before.w, after.w),
        h=mix(before.h, after.h),
        score=min(before.score, after.score),
    )


def find_no_face_ranges(faces: list[FaceBox], duration_ms: int) -> list[NoFaceRange]:
    """Return the stretches longer than `NO_FACE_MIN_MS` (2 s) with no face box.

    Each gap between two consecutive boxes counts, and so do the start of the
    clip before the first box and the end after the last one. A stretch of
    exactly 2 s is not reported. With no boxes at all, the whole clip is one
    stretch (docs/03 §5.3).

    Args:
        faces: Boxes of the main face, sorted by `t_ms`.
        duration_ms: Length of the clip, in milliseconds.

    Returns:
        The stretches in time order, each from the box before it to the box
        after it. Empty if the face never leaves for more than 2 s.

    Example:
        Boxes at 0, 100, 3100 and 4000 ms in a 4100 ms clip: only the gap
        from 100 to 3100 ms (3000 ms) is longer than 2000 ms.

        >>> faces = [
        ...     FaceBox(t_ms=t, x=910, y=490, w=100, h=100, score=0.9)
        ...     for t in (0, 100, 3100, 4000)
        ... ]
        >>> find_no_face_ranges(faces, duration_ms=4100)
        [NoFaceRange(start_ms=100, end_ms=3100)]
        >>> find_no_face_ranges([], duration_ms=5000)
        [NoFaceRange(start_ms=0, end_ms=5000)]
    """
    times = [0, *(box.t_ms for box in faces), duration_ms] if faces else [0, duration_ms]
    return [
        NoFaceRange(start_ms=start, end_ms=end)
        for start, end in pairwise(times)
        if end - start > NO_FACE_MIN_MS
    ]


def _smoothstep(progress: float) -> float:
    """Ease from 0 to 1 with zero speed at both ends: 3p^2 - 2p^3, p clamped to 0..1.

    The zoom curve of docs/03 §5.3. Halfway it is exactly half:
    3 x 0.25 - 2 x 0.125 = 0.5.

    >>> _smoothstep(0.5)
    0.5
    >>> _smoothstep(0.25)
    0.15625
    """
    p = min(max(progress, 0.0), 1.0)
    return p * p * (3 - 2 * p)


def zoom_amount(
    t_ms: int, zoom_at_ms: list[int], ease_ms: int, hold_ms: int = ZOOM_HOLD_MS
) -> float:
    """Return how far into its zoom the camera is: 0 = no zoom, 1 = full zoom.

    Each zoom eases in for `ease_ms`, holds for `hold_ms` and eases out for
    `ease_ms`, both eases along a smoothstep curve (docs/03 §5.3). With the
    defaults that is 1.5 s + 1 s + 1.5 s = 4 s per zoom. If two zooms overlap,
    the larger amount wins.

    Args:
        t_ms: The moment to look at, in clip milliseconds.
        zoom_at_ms: Clip times where each zoom starts to ease in.
        ease_ms: Length of the ease in and of the ease out, in milliseconds.
            `camera_path` uses the middle of the Edit Spec `zoom.ease_s`:
            (1 + 2) / 2 x 1000 = 1500 ms (docs/03 §5.3).
        hold_ms: How long the zoom stays full, in milliseconds.

    Returns:
        A number from 0 to 1.

    Example:
        A zoom at 1000 ms with 1500 ms eases: halfway into the ease in
        (1750 ms) it is 0.5, full from 2500 to 3500 ms, halfway out at
        4250 ms and over at 1000 + 4000 = 5000 ms.

        >>> [zoom_amount(t, [1000], ease_ms=1500) for t in (999, 1750, 3000, 4250, 5000)]
        [0.0, 0.5, 1.0, 0.5, 0.0]
    """
    amount = 0.0
    for zoom_ms in zoom_at_ms:
        into = t_ms - zoom_ms
        if into < 0 or into >= 2 * ease_ms + hold_ms:
            continue
        if into < ease_ms:
            this = _smoothstep(into / ease_ms)
        elif into < ease_ms + hold_ms:
            this = 1.0
        else:
            this = _smoothstep((2 * ease_ms + hold_ms - into) / ease_ms)
        amount = max(amount, this)
    return amount


@dataclass
class _Spring:
    """A critically damped spring on one axis: it reaches the target without bouncing.

    Attributes:
        position: Window center on this axis, in mezzanine pixels.
        velocity: Speed of the center, in pixels per second, between
            -`MAX_SPEED_PX_S` and `MAX_SPEED_PX_S` (600 px/s).
    """

    position: float
    velocity: float = 0.0

    def step(self, target: float, dt: float) -> None:
        """Move one frame toward `target`; `dt` is the frame length in seconds (1 / 30).

        acceleration = omega^2 x (target - position) - 2 x omega x velocity, with
        omega = `SPRING_OMEGA` (8): the pull toward the target minus the damping
        that stops it from overshooting. The velocity is capped at 600 px/s, at
        most 20 px per frame. From rest, 100 px from the target:
        8^2 x 100 = 6400 px/s^2 -> 6400 / 30 = 213.3 px/s -> 213.3 / 30 = 7.1 px.

        >>> spring = _Spring(position=0.0)
        >>> spring.step(target=100.0, dt=1 / 30)
        >>> round(spring.velocity, 1), round(spring.position, 2)
        (213.3, 7.11)
        """
        acceleration = SPRING_OMEGA**2 * (target - self.position) - 2 * SPRING_OMEGA * self.velocity
        self.velocity += acceleration * dt
        self.velocity = min(max(self.velocity, -MAX_SPEED_PX_S), MAX_SPEED_PX_S)
        self.position += self.velocity * dt

    def snap(self, position: float) -> None:
        """Jump straight to `position` and stop, as the camera does on a cut."""
        self.position = position
        self.velocity = 0.0


def _follow(target: float, camera: float, face: float, window_size: int) -> float:
    """Dead zone: only aim at the face once it leaves the central part of the window.

    The central part is `DEAD_ZONE_RATIO` (10 %) of the window size on this axis: on a
    608 px wide window, 608 x 0.10 / 2 = 30.4 px to each side of the camera, and on a
    982 px tall bridge window, 982 x 0.10 / 2 = 49.1 px (docs/03 §5.3). Inside it the
    previous target is kept.

    Args:
        target: Where the camera is aiming now, in mezzanine pixels.
        camera: Current window center, in mezzanine pixels.
        face: Current face center, in mezzanine pixels.
        window_size: Window size on this axis, in pixels.

    Returns:
        The new target: `face` if it is farther than the dead zone from
        `camera`, otherwise `target`.

    >>> _follow(target=960, camera=960, face=985, window_size=608)
    960
    >>> _follow(target=960, camera=960, face=995, window_size=608)
    995
    >>> _follow(target=540, camera=540, face=585, window_size=982)
    540
    >>> _follow(target=540, camera=540, face=595, window_size=982)
    595
    """
    if abs(face - camera) > window_size * DEAD_ZONE_RATIO / 2:
        return face
    return target


def camera_path(
    faces: list[FaceBox],
    frame_w: int,
    frame_h: int,
    duration_ms: int,
    zoom_at_ms: list[int] | None = None,
    cut_at_ms: list[int] | None = None,
    zoom_max_scale: float = 1.15,
    zoom_ease_s: tuple[float, float] = (1.0, 2.0),
    fps: int = 30,
) -> CameraPath:
    """Build one crop keyframe per mezzanine frame that follows the face without shaking.

    There are round(duration_ms x 30 / 1000) frames, the same rounding the
    mezzanine uses to cut its stretches (docs/03 §5.2), and frame n starts at
    round(n x 1000 / 30) ms. On each frame:

    1. The face comes from `face_at`. Each cut is moved to the start of its
       frame, round(ms x 30 / 1000), so the cut frame already sees the new shot.
    2. The scale is base + (zoom_max_scale - base) x `zoom_amount`, where the
       base switches between 1.0 and `BRIDGE_SCALE` (1.10) on every cut; the
       window size comes from `crop_window_size` (docs/03 §5.3).
    3. On each axis the camera aims at the face only once it leaves the dead
       zone (`DEAD_ZONE_RATIO`: 10 % of the window width horizontally and of
       its height vertically), and a critically damped spring moves it there
       at up to `MAX_SPEED_PX_S`. On a cut the camera jumps to the face.
    4. `place_window` keeps the face core visible and the window inside the
       frame. This wins over the top speed: if the face moves faster than the
       spring, the window is pushed along with it.

    With no face boxes at all, the window stays centered in the frame.

    Args:
        faces: Boxes of the main face, in mezzanine pixels, sorted by `t_ms`.
        frame_w: Width of the mezzanine frame, in pixels.
        frame_h: Height of the mezzanine frame, in pixels.
        duration_ms: Length of the clip, in milliseconds (`Timeline.duration_ms`).
        zoom_at_ms: Clip times where each zoom starts, one per zoom emphasis
            (`words_to_clip_ms`, docs/03 §5.3). None means no zooms.
        cut_at_ms: Clip times where the image jumps to the next stretch
            (`Timeline.video_cut_points_ms`). Times at 0 or at the end of the
            clip and later are ignored. None means no cuts.
        zoom_max_scale: Scale at full zoom, Edit Spec `zoom.max_scale`
            (1.15 by default, docs/03 §2.3).
        zoom_ease_s: Edit Spec `zoom.ease_s` as (min, max) seconds, (1, 2) by
            default (docs/03 §2.3). Its middle, 1.5 s, is used for both the
            ease in and the ease out (docs/03 §5.3).
        fps: Frame rate of the mezzanine, 30 (docs/03 §5.2).

    Returns:
        The keyframes, one per frame, and the stretches longer than 2 s with
        no face (`find_no_face_ranges`).

    Raises:
        ValueError: If the frame is narrower than 9:16, or if `zoom_max_scale`
            is below 1 and a zoom is under way (from `crop_window_size`).

    Example:
        A cut at 1753 ms falls on frame round(1753 x 30 / 1000) = 53, which
        starts at round(53 x 1000 / 30) = 1767 ms. Halfway into a zoom during
        a 110 % bridge, the scale is 1.10 + (1.15 - 1.10) x 0.5 = 1.125: a
        540x960 window. Without faces and a cut at 1000 ms, frame 30 switches
        to the 552x982 bridge window, centered: (1920 - 552) / 2 = 684 and
        (1080 - 982) / 2 = 49.

        >>> path = camera_path([], 1920, 1080, duration_ms=2000, cut_at_ms=[1000])
        >>> len(path.keyframes)
        60
        >>> path.keyframes[29]
        CropKeyframe(t_ms=967, x=656, y=0, w=608, h=1080)
        >>> path.keyframes[30]
        CropKeyframe(t_ms=1000, x=684, y=49, w=552, h=982)
    """
    zooms = zoom_at_ms or []
    cut_frames = {round(ms * fps / 1000) for ms in cut_at_ms or [] if 0 < ms < duration_ms}
    # Cuts moved to the start of their frame, so the cut frame already sees the new shot.
    cut_frame_ms = sorted(round(frame * 1000 / fps) for frame in cut_frames)
    ease_ms = round((zoom_ease_s[0] + zoom_ease_s[1]) / 2 * 1000)
    dt = 1 / fps

    first = face_at(faces, 0)
    start_x = first.x + first.w / 2 if first else frame_w / 2
    start_y = first.y + first.h / 2 if first else frame_h / 2
    spring_x, spring_y = _Spring(start_x), _Spring(start_y)
    target_x, target_y = start_x, start_y
    base_scale = 1.0

    keyframes: list[CropKeyframe] = []
    # Same rounding as the mezzanine (ffmpeg_args.frame_counts): one keyframe per real frame.
    for frame in range(round(duration_ms * fps / 1000)):
        t_ms = round(frame * 1000 / fps)
        face = face_at(faces, t_ms, cut_frame_ms)
        is_cut = frame in cut_frames
        if is_cut:
            base_scale = BRIDGE_SCALE if base_scale == 1.0 else 1.0

        scale = base_scale + (zoom_max_scale - base_scale) * zoom_amount(t_ms, zooms, ease_ms)
        w, h = crop_window_size(frame_w, frame_h, scale)

        if face is None:
            x = (frame_w - w) / 2
            y = (frame_h - h) / 2
        else:
            face_x, face_y = face.x + face.w / 2, face.y + face.h / 2
            if is_cut:
                spring_x.snap(face_x)
                spring_y.snap(face_y)
                target_x, target_y = face_x, face_y
            else:
                target_x = _follow(target_x, spring_x.position, face_x, w)
                target_y = _follow(target_y, spring_y.position, face_y, h)
                spring_x.step(target_x, dt)
                spring_y.step(target_y, dt)

            x = place_window(spring_x.position, w, face.x, face.w, frame_w)
            y = place_window(spring_y.position, h, face.y, face.h, frame_h)
            spring_x.position = x + w / 2
            spring_y.position = y + h / 2

        keyframes.append(CropKeyframe(t_ms=t_ms, x=round(x), y=round(y), w=w, h=h))

    return CameraPath(keyframes=keyframes, no_face=find_no_face_ranges(faces, duration_ms))
