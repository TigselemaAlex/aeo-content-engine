from content_engine.piece_types.clip.domain.path_checks import PathReport
from content_engine.piece_types.clip.domain.verify import Check, FrameMatch, VideoInfo, verify_clip

GOOD_INFO = VideoInfo(
    width=1080,
    height=1920,
    fps=30,
    frames=4,
    video_duration_ms=133.3,
    audio_duration_ms=140,
)
GOOD_PATH = PathReport(
    frames=4, face_cut_frames=[], worst_face_cut=0.02, jumps=[], largest_move_px=3, wobbles=[]
)


def matches(neighbour_db: float | None = 30.0) -> list[FrameMatch]:
    return [FrameMatch(frame=i, own_db=44.0, neighbour_db=neighbour_db) for i in range(4)]


def failed(checks: list[Check]) -> list[str]:
    return [check.name for check in checks if not check.ok]


def test_good_clip_passes_every_check() -> None:
    checks = verify_clip(GOOD_INFO, matches(), GOOD_PATH, cut_frames=[2])

    assert failed(checks) == []
    assert len(checks) == 10


def test_frame_closer_to_a_neighbour_window_fails() -> None:
    late = matches()
    late[2] = FrameMatch(frame=2, own_db=36.0, neighbour_db=45.0)

    checks = verify_clip(GOOD_INFO, late, GOOD_PATH, cut_frames=[2])

    assert failed(checks) == ["frames on their window", "bridges on their cut"]


def test_neighbour_within_half_a_db_is_a_tie_not_a_miss() -> None:
    checks = verify_clip(GOOD_INFO, matches(neighbour_db=44.4), GOOD_PATH, cut_frames=[])

    assert failed(checks) == []


def test_audio_more_than_one_frame_off_fails() -> None:
    info = GOOD_INFO.model_copy(update={"audio_duration_ms": 133.3 + 34})

    assert failed(verify_clip(info, matches(), GOOD_PATH, cut_frames=[])) == ["audio sync"]


def test_missing_audio_or_frames_fail() -> None:
    info = GOOD_INFO.model_copy(update={"audio_duration_ms": None, "frames": 3})

    assert failed(verify_clip(info, matches(), GOOD_PATH, cut_frames=[])) == [
        "frames",
        "audio sync",
    ]


def test_path_problems_fail_their_checks() -> None:
    path = GOOD_PATH.model_copy(update={"face_cut_frames": [1], "jumps": [2], "wobbles": [3]})

    assert failed(verify_clip(GOOD_INFO, matches(), path, cut_frames=[])) == [
        "face inside window",
        "jumps outside cuts",
        "wobbles",
    ]
