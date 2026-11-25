"""Face boxes and the rule that picks the main face of a clip.

All positions are in pixels of the full-size mezzanine (not the ~640 px copy the detector
reads) and all times in milliseconds from the start of the mezzanine (docs/03 §5.3).
"""

import math

from pydantic import BaseModel, ConfigDict, Field

MAX_JUMP_RATIO = 0.5
"""Farthest a face can move between two boxes and stay in its track, in face widths.

The distance is measured between box centers, in widths of the track's last box.
Product rule: 0.5 face widths (docs/03 §5.3, docs/00 "Cara principal").
"""


class FaceBox(BaseModel):
    """A detected face at one moment, in original video pixels.

    (x, y) is the top-left corner. x and y can be negative when the face
    is partly out of frame.

    Attributes:
        t_ms: When the face was seen, in milliseconds from the start of the mezzanine.
            0 or more. The detector samples at 10 fps, so boxes come every ~100 ms
            (docs/03 §5.3).
        x: Left edge of the box, in mezzanine pixels. Can be negative.
        y: Top edge of the box, in mezzanine pixels. Can be negative.
        w: Width of the box, in mezzanine pixels. More than 0.
        h: Height of the box, in mezzanine pixels. More than 0.
        score: Detector confidence, from 0 to 1. `pick_main_face` does not use it.
    """

    t_ms: int = Field(ge=0)
    x: int
    y: int
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    score: float = Field(ge=0, le=1)

    model_config = ConfigDict(frozen=True)


def _center(box: FaceBox) -> tuple[float, float]:
    """Return the `(x, y)` center of the box: `(x + w / 2, y + h / 2)`, in pixels."""
    return box.x + box.w / 2, box.y + box.h / 2


def _distance(a: FaceBox, b: FaceBox) -> float:
    """Return the straight-line distance between the centers of two boxes, in pixels."""
    ax, ay = _center(a)
    bx, by = _center(b)
    return math.hypot(ax - bx, ay - by)


def _total_area(track: list[FaceBox]) -> int:
    """Return the sum of `w x h` over every box of the track, in square pixels."""
    return sum(box.w * box.h for box in track)


def pick_main_face(boxes: list[FaceBox]) -> list[FaceBox]:
    """Return the boxes of the biggest, most persistent face, sorted by time.

    Boxes are grouped into tracks: a box joins the nearest track whose last
    box is from an earlier frame and within MAX_JUMP_RATIO face widths.
    The track with the largest total area wins. There is no time limit, so
    a face that comes back to the same place rejoins its track.

    Boxes are read in time order, whatever the input order. A box is only compared
    with the last box of each track, so a face that drifts slowly stays in one track.
    Two boxes from the same moment never share a track. The total area (sum of
    `w x h`) joins "big" and "persistent" in one number, so a false or background
    face seen for a few frames loses to the speaker (docs/03 §5.3, docs/00
    "Cara principal"). On a tie, the track that started first wins.

    Args:
        boxes: Every face the detector found in the mezzanine, in any order. A moment
            can have zero, one or several boxes.

    Returns:
        The boxes of the winning track, sorted by `t_ms`, with at most one box per
        moment. An empty list if `boxes` is empty.

    Example:
        On a 1920x1080 mezzanine, say the speaker's face is 500x500 at x=800 at 0 ms,
        centered at (800 + 500 / 2, 200 + 500 / 2) = (1050, 450). At 100 ms it is at
        x=1000, center (1250, 450): it moved 200 px, within 0.5 x 500 = 250 px, so it
        joins the same track. A bigger 600x600 box at (100, 100) shows up only at 0 ms.
        Areas: speaker 2 x 500 x 500 = 500000, other 600 x 600 = 360000, so the
        speaker wins.

        >>> boxes = [
        ...     FaceBox(t_ms=0, x=800, y=200, w=500, h=500, score=0.9),
        ...     FaceBox(t_ms=0, x=100, y=100, w=600, h=600, score=0.8),
        ...     FaceBox(t_ms=100, x=1000, y=200, w=500, h=500, score=0.9),
        ... ]
        >>> [(box.t_ms, box.x) for box in pick_main_face(boxes)]
        [(0, 800), (100, 1000)]

        Had it moved 300 px (x=1100), 300 > 250 starts a new track. The speaker is
        split into two tracks of 250000 each, and the 600x600 box (360000) wins:

        >>> jumped = [*boxes[:2], FaceBox(t_ms=100, x=1100, y=200, w=500, h=500, score=0.9)]
        >>> [(box.t_ms, box.x) for box in pick_main_face(jumped)]
        [(0, 100)]
    """
    tracks: list[list[FaceBox]] = []

    for box in sorted(boxes, key=lambda box: box.t_ms):
        candidates = [
            track
            for track in tracks
            if track[-1].t_ms < box.t_ms
            and _distance(box, track[-1]) <= MAX_JUMP_RATIO * track[-1].w
        ]
        if candidates:
            nearest = min(candidates, key=lambda track: _distance(box, track[-1]))
            nearest.append(box)
        else:
            tracks.append([box])
    if not tracks:
        return []
    return max(tracks, key=_total_area)
