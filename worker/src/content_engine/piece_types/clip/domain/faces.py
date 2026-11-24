import math

from pydantic import BaseModel, ConfigDict, Field

MAX_JUMP_RATIO = 0.5


class FaceBox(BaseModel):
    """A detected face at one moment, in original video pixels.

    (x, y) is the top-left corner. x and y can be negative when the face
    is partly out of frame.
    """

    t_ms: int = Field(ge=0)
    x: int
    y: int
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    score: float = Field(ge=0, le=1)

    model_config = ConfigDict(frozen=True)


def _center(box: FaceBox) -> tuple[float, float]:
    return box.x + box.w / 2, box.y + box.h / 2


def _distance(a: FaceBox, b: FaceBox) -> float:
    ax, ay = _center(a)
    bx, by = _center(b)
    return math.hypot(ax - bx, ay - by)


def _total_area(track: list[FaceBox]) -> int:
    return sum(box.w * box.h for box in track)


def pick_main_face(boxes: list[FaceBox]) -> list[FaceBox]:
    """Return the boxes of the biggest, most persistent face, sorted by time.

    Boxes are grouped into tracks: a box joins the nearest track whose last
    box is from an earlier frame and within MAX_JUMP_RATIO face widths.
    The track with the largest total area wins. There is no time limit, so
    a face that comes back to the same place rejoins its track.
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
