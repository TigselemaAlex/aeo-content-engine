"""Turn the measurements of a composed vertical clip into pass or fail checks, for `verify-clip`.

Pure code: the media adapter (`clip_probe.py`) measures the clip and compares its frames
with the mezzanine, `check_path` checks the camera path, and this module only applies the
limits. Sizes are pixels of the output video (1080x1920), durations are milliseconds of
the clip, frames are frames of the mezzanine at 30 fps, and frame matches are PSNR in
decibels (dB): the higher, the closer two images are.
"""

from pydantic import BaseModel, ConfigDict

from content_engine.piece_types.clip.domain.camera_path import (
    FACE_CROP_TOLERANCE,
    MAX_SPEED_PX_S,
    CropKeyframe,
)
from content_engine.piece_types.clip.domain.ffmpeg_args import OUTPUT_H, OUTPUT_W
from content_engine.piece_types.clip.domain.path_checks import PathReport

MIN_OWN_MATCH_DB = 35.0
"""Lowest match, in dB, between an output frame and its own window of the mezzanine.

Below it the frame does not show the window it should. Approved by Alex on 26 nov 2026;
on the test stretch (words 29 to 108, 1004 frames) the worst frame matches at 43.9 dB.
"""

NEIGHBOUR_MARGIN_DB = 0.5
"""How much better, in dB, a neighbour's window must match a frame to count as a miss.

When the windows of two frames are 1 px apart their crops look almost the same, and
either can match a little better by chance. The margin keeps those ties from counting as
frames on the wrong window (approved by Alex on 26 nov 2026).
"""

MAX_AV_OFFSET_FRAMES = 1
"""Largest difference between the video and audio durations, in frames.

1 frame is 1000 / 30 = 33.3 ms at 30 fps. Approved by Alex on 26 nov 2026; measured on
the test stretch: 9.3 ms (1004 frames = 33466.7 ms of video against 33476 ms of audio).
"""


class VideoInfo(BaseModel):
    """What ffprobe reports about a video, read by `probe_video`.

    Attributes:
        width: Width of the video, in pixels.
        height: Height of the video, in pixels.
        fps: Frame rate of the video stream (`r_frame_rate`), in frames per second.
        frames: Frames counted by decoding the whole video stream.
        video_duration_ms: Length of the video stream, in milliseconds.
        audio_duration_ms: Length of the audio stream, in milliseconds. None if the
            video has no audio.
    """

    width: int
    height: int
    fps: float
    frames: int
    video_duration_ms: float
    audio_duration_ms: float | None

    model_config = ConfigDict(frozen=True)


class FrameMatch(BaseModel):
    """How well one output frame matches its own crop window and its neighbours'.

    `match_frames` shrinks the output frame back to the window size and compares it,
    in gray, with the mezzanine frame cropped at its own keyframe and at the keyframes
    of the frames before and after. A frame on its right window matches its own crop
    best; a frame one frame late or early matches a neighbour's.

    Attributes:
        frame: Index of the frame, 0 or more.
        own_db: Match with its own window, in dB (PSNR). Test stretch: 43.9 dB at
            worst; 49.4 dB on the cut frame 96.
        neighbour_db: Best match with the window of the previous or next frame, in dB,
            counting only neighbours whose window differs from this one
            (`windows_to_compare`). None when neither does. Test stretch: 16.3 dB on
            the cut frame 96, against the 608x1080 window of frame 95.
    """

    frame: int
    own_db: float
    neighbour_db: float | None

    model_config = ConfigDict(frozen=True)

    @property
    def neighbour_wins(self) -> bool:
        """Whether a neighbour's window matches better by more than `NEIGHBOUR_MARGIN_DB`.

        True means the frame shows the wrong window: neighbour_db > own_db + 0.5.

        >>> FrameMatch(frame=2, own_db=36.0, neighbour_db=45.0).neighbour_wins
        True
        >>> FrameMatch(frame=2, own_db=44.0, neighbour_db=44.4).neighbour_wins
        False
        >>> FrameMatch(frame=0, own_db=47.3, neighbour_db=None).neighbour_wins
        False
        """
        if self.neighbour_db is None:
            return False
        return self.neighbour_db > self.own_db + NEIGHBOUR_MARGIN_DB


class Check(BaseModel):
    """One line of the `verify-clip` report.

    Attributes:
        name: What is checked, such as `"audio sync"`.
        value: What was measured, as text for the report, such as `"9.3 ms"`.
        limit: What it must be, as text for the report, such as `"<= 33.3 ms"`.
        ok: Whether the value is within the limit.
        blocking: Whether a value outside the limit fails `verify-clip`. When False,
            it is only reported as a warning (`WARN`) and the command still exits
            with code 0. True by default; only `captions in safe zone` is False
            (docs/03 §5.7).
    """

    name: str
    value: str
    limit: str
    ok: bool
    blocking: bool = True

    model_config = ConfigDict(frozen=True)


def windows_to_compare(keyframes: list[CropKeyframe], frame: int) -> list[CropKeyframe]:
    """Return the neighbour windows an output frame is compared with, besides its own.

    The neighbours are the previous and the next frame, and each counts only when its
    window (x, y, w and h; `t_ms` is not compared) differs from the frame's own: the
    same window would give the same match and tell nothing. The first and the last
    frame have one neighbour each. `match_frames` crops the mezzanine at these windows;
    the rule lives here, in pure code, so it is tested without a video.

    Args:
        keyframes: One crop window per mezzanine frame, in frame order, from
            `camera_path`.
        frame: Index of the frame, from 0 to len(keyframes) - 1.

    Returns:
        0, 1 or 2 keyframes, the previous frame's first. Empty when both neighbours
        share the frame's window.

    Example:
        On the test stretch (words 29 to 108, 1004 frames) 355 frames get an empty
        list. Frame 96, the first cut bridge (552x982 at x 946), gets only the 608x1080
        window of frame 95: frame 97 keeps the bridge window. Below, frame 0 has the
        same window as frame 1, and frame 1 only differs from frame 2:

        >>> keyframes = [
        ...     CropKeyframe(t_ms=0, x=820, y=0, w=608, h=1080),
        ...     CropKeyframe(t_ms=33, x=820, y=0, w=608, h=1080),
        ...     CropKeyframe(t_ms=67, x=822, y=0, w=608, h=1080),
        ... ]
        >>> windows_to_compare(keyframes, 0)
        []
        >>> windows_to_compare(keyframes, 1)
        [CropKeyframe(t_ms=67, x=822, y=0, w=608, h=1080)]
    """
    own = keyframes[frame]
    return [
        keyframes[other]
        for other in (frame - 1, frame + 1)
        if 0 <= other < len(keyframes)
        and (keyframes[other].x, keyframes[other].y, keyframes[other].w, keyframes[other].h)
        != (own.x, own.y, own.w, own.h)
    ]


def frame_list(items: list[int], limit: int = 8) -> str:
    """Write a list of frames for the report: how many, then the first `limit` of them.

    Used in the values of `verify_clip` and of the caption checks (`caption_checks.py`),
    so a long list of frames fits on one line of the `verify-clip` report.

    Args:
        items: Frame indices, in the order to show them.
        limit: Most frames written out; the rest become `...`. 8 by default.

    Returns:
        `"0"` for an empty list, otherwise the count and the first frames in brackets.

    Example:
        Test stretch, with captions: 1002 frames leave the safe zone, written
        `1002 (2, 3, 4, 5, 6, 7, 8, 9, ...)`.

        >>> frame_list([])
        '0'
        >>> frame_list([96, 167])
        '2 (96, 167)'
        >>> frame_list(list(range(10)))
        '10 (0, 1, 2, 3, 4, 5, 6, 7, ...)'
    """
    shown = ", ".join(str(i) for i in items[:limit])
    return f"{len(items)} ({shown}{', ...' if len(items) > limit else ''})" if items else "0"


def verify_clip(
    info: VideoInfo,
    matches: list[FrameMatch],
    path: PathReport,
    cut_frames: list[int],
    fps: int = 30,
) -> list[Check]:
    """Check a composed vertical clip against the limits of `verify-clip`.

    Returns ten checks, always in this order (limits approved by Alex on 26 nov 2026):

    1. `size`: the clip is `OUTPUT_W` x `OUTPUT_H` = 1080x1920 (docs/03 §5.6).
    2. `fps`: it runs at `fps`, 30 (docs/03 §5.6).
    3. `frames`: one frame per keyframe of the camera path.
    4. `audio sync`: it has audio, and the video and audio durations differ by at most
       `MAX_AV_OFFSET_FRAMES` = 1 frame, 1000 / 30 = 33.3 ms.
    5. `frames on their window`: no frame matches a neighbour's window better
       (`FrameMatch.neighbour_wins`), and every frame was compared.
    6. `worst frame match`: every frame matches its own window at `MIN_OWN_MATCH_DB`
       (35 dB) or more. 0 dB if there are no matches, which fails.
    7. `bridges on their cut`: every cut frame is on its own window, by the two checks
       above, so each cut bridge starts on the frame of its cut.
    8. `face inside window`: no frame cuts the face more than `allowed_cut` permits
       (`FACE_CROP_TOLERANCE`, 5 % per side, or centered if it does not fit).
    9. `jumps outside cuts`: no move faster than `MAX_SPEED_PX_S` / fps =
       600 / 30 = 20 px per frame.
    10. `wobbles`: no a -> b -> a of the window center.

    Args:
        info: What `probe_video` read from the clip.
        matches: One match per output frame, from `match_frames`.
        path: What `check_path` found on the camera path the clip was made with.
        cut_frames: Frames of the cuts, from `cut_at_frames`.
        fps: Frame rate the clip must have. 30 by default (docs/03 §5.6).

    Returns:
        The ten checks. The clip passes if all of them are `ok`.

    Example:
        Test stretch (words 29 to 108, 9 cuts): ffprobe reads 1080x1920 at 30 fps,
        1004 frames, 33466.7 ms of video and 33476 ms of audio, so the audio is off by
        9.3 ms; the worst frame matches at 43.9 dB, the worst face cut is 5.4 % and
        the largest move 17.0 px. All ten checks pass.

        >>> info = VideoInfo(
        ...     width=1080, height=1920, fps=30.0, frames=1004,
        ...     video_duration_ms=33466.667, audio_duration_ms=33476.0,
        ... )
        >>> matches = [FrameMatch(frame=i, own_db=43.9, neighbour_db=None) for i in range(1004)]
        >>> path = PathReport(
        ...     frames=1004, face_cut_frames=[], worst_face_cut=0.054, jumps=[],
        ...     largest_move_px=17.0, wobbles=[],
        ... )
        >>> cuts = [96, 167, 201, 380, 460, 532, 721, 803, 904]
        >>> checks = verify_clip(info, matches, path, cut_frames=cuts)
        >>> checks[3]
        Check(name='audio sync', value='9.3 ms', limit='<= 33.3 ms', ok=True, blocking=True)
        >>> sum(check.ok for check in checks)
        10
    """
    frame_ms = 1000 / fps
    checks = [
        Check(
            name="size",
            value=f"{info.width}x{info.height}",
            limit=f"{OUTPUT_W}x{OUTPUT_H}",
            ok=(info.width, info.height) == (OUTPUT_W, OUTPUT_H),
        ),
        Check(name="fps", value=f"{info.fps:g}", limit=str(fps), ok=info.fps == fps),
        Check(
            name="frames",
            value=str(info.frames),
            limit=f"{path.frames} (one per keyframe)",
            ok=info.frames == path.frames,
        ),
    ]

    if info.audio_duration_ms is None:
        checks.append(Check(name="audio sync", value="no audio", limit="audio present", ok=False))
    else:
        offset = abs(info.video_duration_ms - info.audio_duration_ms)
        checks.append(
            Check(
                name="audio sync",
                value=f"{offset:.1f} ms",
                limit=f"<= {MAX_AV_OFFSET_FRAMES * frame_ms:.1f} ms",
                ok=offset <= MAX_AV_OFFSET_FRAMES * frame_ms,
            )
        )

    off_frames = [m.frame for m in matches if m.neighbour_wins]
    worst_own = min((m.own_db for m in matches), default=0.0)
    checks.append(
        Check(
            name="frames on their window",
            value=f"{frame_list(off_frames)} off",
            limit="0 off",
            ok=not off_frames and len(matches) == path.frames,
        )
    )
    checks.append(
        Check(
            name="worst frame match",
            value=f"{worst_own:.1f} dB",
            limit=f">= {MIN_OWN_MATCH_DB:g} dB",
            ok=worst_own >= MIN_OWN_MATCH_DB,
        )
    )

    by_frame = {m.frame: m for m in matches}
    on_time = [
        frame
        for frame in cut_frames
        if frame in by_frame
        and not by_frame[frame].neighbour_wins
        and by_frame[frame].own_db >= MIN_OWN_MATCH_DB
    ]
    checks.append(
        Check(
            name="bridges on their cut",
            value=f"{len(on_time)}/{len(cut_frames)}",
            limit=f"{len(cut_frames)}/{len(cut_frames)}",
            ok=len(on_time) == len(cut_frames),
        )
    )

    checks.extend(
        [
            Check(
                name="face inside window",
                value=(
                    f"{frame_list(path.face_cut_frames)} frames over; "
                    f"worst {path.worst_face_cut:.1%}"
                ),
                limit=(
                    f"0 frames over {FACE_CROP_TOLERANCE:.0%} per side "
                    "(or centered if it does not fit)"
                ),
                ok=not path.face_cut_frames,
            ),
            Check(
                name="jumps outside cuts",
                value=f"{frame_list(path.jumps)}; largest {path.largest_move_px:.1f} px",
                limit=f"0 over {MAX_SPEED_PX_S / fps:g} px/frame",
                ok=not path.jumps,
            ),
            Check(
                name="wobbles",
                value=frame_list(path.wobbles),
                limit="0",
                ok=not path.wobbles,
            ),
        ]
    )
    return checks
