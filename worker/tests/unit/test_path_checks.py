from content_engine.piece_types.clip.domain.camera_path import CropKeyframe
from content_engine.piece_types.clip.domain.faces import FaceBox
from content_engine.piece_types.clip.domain.path_checks import allowed_cut, check_path


def window(frame: int, x: int, w: int = 608, y: int = 0, h: int = 1080) -> CropKeyframe:
    return CropKeyframe(t_ms=round(frame * 1000 / 30), x=x, y=y, w=w, h=h)


def face(t_ms: int, x: int, w: int = 400) -> FaceBox:
    return FaceBox(t_ms=t_ms, x=x, y=300, w=w, h=w, score=0.9)


STILL_FACE = [face(t, x=760) for t in range(0, 2000, 100)]


def test_still_window_on_a_still_face_passes() -> None:
    report = check_path(
        [window(i, x=656) for i in range(30)], STILL_FACE, cut_frames=[], frame_w=1920, frame_h=1080
    )

    assert report.frames == 30
    assert (report.face_cut_frames, report.jumps, report.wobbles) == ([], [], [])
    assert report.largest_move_px == 0


def test_back_and_forth_is_a_wobble() -> None:
    xs = [656, 656, 657, 656, 656]

    report = check_path(
        [window(i, x=x) for i, x in enumerate(xs)],
        STILL_FACE,
        cut_frames=[],
        frame_w=1920,
        frame_h=1080,
    )

    assert report.wobbles == [2]


def test_steady_move_is_not_a_wobble() -> None:
    xs = [656, 657, 658, 659, 660]

    report = check_path(
        [window(i, x=x) for i, x in enumerate(xs)],
        STILL_FACE,
        cut_frames=[],
        frame_w=1920,
        frame_h=1080,
    )

    assert report.wobbles == []


def test_move_faster_than_top_speed_is_a_jump_unless_on_a_cut() -> None:
    # 600 px/s at 30 fps is 20 px per frame.
    xs = [656, 656, 680, 680, 704]

    report = check_path(
        [window(i, x=x) for i, x in enumerate(xs)],
        STILL_FACE,
        cut_frames=[4],
        frame_w=1920,
        frame_h=1080,
    )

    assert report.jumps == [2]
    assert report.largest_move_px == 24


def test_face_cut_past_five_percent_is_reported() -> None:
    # 400 px face from 760 to 1160; a 608 window from 580 ends at 1188, inside.
    # From 532 it ends at 1140: 20 px out = 5 %, allowed. From 520: 32 px = 8 %.
    keyframes = [window(0, x=580), window(1, x=532), window(2, x=520)]

    report = check_path(keyframes, STILL_FACE, cut_frames=[], frame_w=1920, frame_h=1080)

    assert report.face_cut_frames == [2]
    assert report.worst_face_cut == 0.08


def test_face_wider_than_window_may_lose_half_the_excess_per_side() -> None:
    # Test stretch, frame 225: a 615 px face in a 552 px window loses (615 - 552) / 2
    # = 31.5 px per side, more than 5 % (30.75 px), as docs/03 §5.3 centers it.
    assert allowed_cut(size=552, face_size=615) * 615 == 32.5
    assert allowed_cut(size=608, face_size=400) * 400 == 21


def test_face_out_of_the_frame_is_not_blamed_on_the_window() -> None:
    # A 550 px face from x = -40: 40 px are outside the video, so a window at x = 0
    # cuts nothing that it could have kept (docs/03 §5.3: boxes can be negative).
    faces = [face(t, x=-40, w=550) for t in range(0, 2000, 100)]

    report = check_path([window(i, x=0) for i in range(5)], faces, [], frame_w=1920, frame_h=1080)

    assert report.face_cut_frames == []
    assert report.worst_face_cut == 0
