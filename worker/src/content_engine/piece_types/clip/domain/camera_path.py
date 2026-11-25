"""Camera path: where the vertical 9:16 window sits on every frame of the mezzanine.

All positions are in mezzanine pixels and all times in clip milliseconds.
"""

from bisect import bisect_right
from dataclasses import dataclass
from itertools import pairwise

from pydantic import BaseModel, ConfigDict, Field

from content_engine.piece_types.clip.domain.faces import FaceBox

DEAD_ZONE_RATIO = 0.10
SPRING_OMEGA = 8.0
MAX_SPEED_PX_S = 600.0
FACE_CROP_TOLERANCE = 0.05
BRIDGE_SCALE = 1.10
ZOOM_HOLD_MS = 1000
FACE_GAP_MS = 200
NO_FACE_MIN_MS = 2000


class CropKeyframe(BaseModel):
    """The crop window on one frame. (x, y) is the top-left corner."""

    t_ms: int = Field(ge=0)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)

    model_config = ConfigDict(frozen=True)


class NoFaceRange(BaseModel):
    """A stretch of the clip with no face for longer than NO_FACE_MIN_MS."""

    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)

    model_config = ConfigDict(frozen=True)


class CameraPath(BaseModel):
    keyframes: list[CropKeyframe]
    no_face: list[NoFaceRange]

    model_config = ConfigDict(frozen=True)


def _even(value: float) -> int:
    return 2 * round(value / 2)


def crop_window_size(frame_w: int, frame_h: int, scale: float = 1.0) -> tuple[int, int]:
    """Size of the 9:16 window: full height, width = height * 9 / 16, shrunk by scale.

    Both sides are rounded to even numbers because yuv420p video needs them.
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
    """Start (left or top edge) of the window on one axis.

    The window is centered on `center`, then moved just enough to keep the
    face inside it. Up to FACE_CROP_TOLERANCE of the face may be left out on
    each side, so the noisy edges of the detected box do not shake the
    window. If even that is bigger than the window, the window is centered
    on the face so both sides lose the same amount. Last, the window is kept
    inside the frame.
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
    """The face at any moment, from boxes sampled every ~100 ms.

    Between two close boxes the position is interpolated in a straight line,
    except across a cut: the two boxes belong to different shots, so the box
    on the same side of the cut as t_ms is used. Across a gap longer than
    FACE_GAP_MS the last box is held; before the first box, the first box
    is used.
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
    """Stretches longer than NO_FACE_MIN_MS with no face box."""
    times = [0, *(box.t_ms for box in faces), duration_ms] if faces else [0, duration_ms]
    return [
        NoFaceRange(start_ms=start, end_ms=end)
        for start, end in pairwise(times)
        if end - start > NO_FACE_MIN_MS
    ]


def _smoothstep(progress: float) -> float:
    p = min(max(progress, 0.0), 1.0)
    return p * p * (3 - 2 * p)


def zoom_amount(
    t_ms: int, zoom_at_ms: list[int], ease_ms: int, hold_ms: int = ZOOM_HOLD_MS
) -> float:
    """How far into its zoom the camera is: 0 = no zoom, 1 = full zoom.

    Each zoom eases in for ease_ms, holds for hold_ms and eases out for ease_ms.
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
    """A critically damped spring on one axis: it reaches the target without bouncing."""

    position: float
    velocity: float = 0.0

    def step(self, target: float, dt: float) -> None:
        acceleration = SPRING_OMEGA**2 * (target - self.position) - 2 * SPRING_OMEGA * self.velocity
        self.velocity += acceleration * dt
        self.velocity = min(max(self.velocity, -MAX_SPEED_PX_S), MAX_SPEED_PX_S)
        self.position += self.velocity * dt

    def snap(self, position: float) -> None:
        self.position = position
        self.velocity = 0.0


def _follow(target: float, camera: float, face: float, window_size: int) -> float:
    """Dead zone: only aim at the face once it leaves the central part of the window."""
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
    """One crop keyframe per frame that follows the face without shaking.

    zoom_at_ms and cut_at_ms are in clip time. On each cut the framing
    switches between 100 % and BRIDGE_SCALE and the camera jumps to the face.
    Keeping the face core visible wins over MAX_SPEED_PX_S: if the face
    moves faster than the spring, the window is pushed along with it.
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
