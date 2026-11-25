import pytest

from content_engine.piece_types.clip.domain.camera_path import (
    MAX_SPEED_PX_S,
    CropKeyframe,
    NoFaceRange,
    camera_path,
    crop_window_size,
    face_at,
    find_no_face_ranges,
    place_window,
    zoom_amount,
)
from content_engine.piece_types.clip.domain.faces import FaceBox

FRAME_W, FRAME_H = 1920, 1080


def make_box(t_ms: int, center_x: int, w: int = 100, y: int = 490) -> FaceBox:
    return FaceBox(t_ms=t_ms, x=center_x - w // 2, y=y, w=w, h=w, score=0.9)


def still_face(center_x: int, duration_ms: int, w: int = 100) -> list[FaceBox]:
    return [make_box(t, center_x, w) for t in range(0, duration_ms, 100)]


def center_x(keyframe: CropKeyframe) -> float:
    return keyframe.x + keyframe.w / 2


# Step 1 · window size


def test_window_is_9_16_of_the_real_height() -> None:
    assert crop_window_size(1920, 1080) == (608, 1080)
    # 720 * 9 / 16 = 405 sits halfway between 404 and 406; Python rounds halves to even.
    assert crop_window_size(1280, 720) == (404, 720)


def test_window_shrinks_with_scale_and_stays_even() -> None:
    assert crop_window_size(FRAME_W, FRAME_H, scale=1.10) == (552, 982)
    assert crop_window_size(FRAME_W, FRAME_H, scale=1.15) == (528, 940)


def test_window_rejects_scale_below_one_and_vertical_frames() -> None:
    with pytest.raises(ValueError, match="scale"):
        crop_window_size(FRAME_W, FRAME_H, scale=0.9)
    with pytest.raises(ValueError, match="too narrow"):
        crop_window_size(500, 1080)


# Step 2 · center on the face without leaving the frame


def test_window_centers_on_the_face() -> None:
    # Face from 849 to 1398: center 1123.5, window starts at 1123.5 - 304.
    assert place_window(1123.5, 608, 849, 549, FRAME_W) == 819.5


def test_face_at_the_left_edge_keeps_window_inside_frame() -> None:
    assert place_window(274.5, 608, 0, 549, FRAME_W) == 0


def test_face_at_the_right_edge_keeps_window_inside_frame() -> None:
    assert place_window(1645.5, 608, 1371, 549, FRAME_W) == 1312


def test_window_moves_just_enough_to_keep_the_face_core_inside() -> None:
    # Face from 1000 to 1549. 5 % of 549 = 27.45 px may stay out on each side,
    # so the core ends at 1549 - 27.45 = 1521.55 and the window must start at
    # 1521.55 - 608 = 913.55 or later.
    assert place_window(960, 608, 1000, 549, FRAME_W) == pytest.approx(913.55)


def test_zoomed_window_still_fits_the_face_core() -> None:
    # Zoom to 1.15: window 528. The core of a 549 face is 549 * 0.9 = 494.1, so it fits.
    start = place_window(1123.5, 528, 849, 549, FRAME_W)

    assert start == 1123.5 - 264
    assert start <= 849 + 27.45
    assert start + 528 >= 1398 - 27.45


def test_face_bigger_than_window_loses_the_same_on_both_sides() -> None:
    # A 600 face has a 540 core, more than a 528 window: center on the face.
    # Face center 849 + 300 = 1149, so the window starts at 1149 - 264 = 885.
    assert place_window(960, 528, 849, 600, FRAME_W) == 885


# Step 3 · dead zone


def test_small_face_moves_do_not_move_the_window() -> None:
    wobble = [960, 980, 940, 985, 935, 960]  # all within ±30 px of the window center
    faces = [make_box(k * 100, cx) for k, cx in enumerate(wobble * 5)]

    path = camera_path(faces, FRAME_W, FRAME_H, duration_ms=3000)

    assert {keyframe.x for keyframe in path.keyframes} == {960 - 304}


# Step 4 · smoothing and max speed


def test_big_jump_is_followed_smoothly_and_without_overshoot() -> None:
    faces = still_face(700, 1000) + [make_box(t, 900) for t in range(1000, 4000, 100)]

    path = camera_path(faces, FRAME_W, FRAME_H, duration_ms=4000)
    centers = [center_x(keyframe) for keyframe in path.keyframes]
    steps = [after - before for before, after in zip(centers, centers[1:], strict=False)]

    assert max(abs(step) for step in steps) <= MAX_SPEED_PX_S / 30 + 1
    assert sum(1 for step in steps if step > 0) > 10
    assert max(centers) <= 901
    assert centers[-1] == pytest.approx(900, abs=1)


# Step 5 · zooms


def test_zoom_eases_in_holds_and_eases_out() -> None:
    def amount(t_ms: int) -> float:
        return zoom_amount(t_ms, [1000], ease_ms=1500, hold_ms=1000)

    assert amount(999) == 0
    assert amount(1000 + 750) == pytest.approx(0.5)
    assert amount(1000 + 2000) == 1
    assert amount(1000 + 3250) == pytest.approx(0.5)
    assert amount(1000 + 4000) == 0


def test_zoom_shrinks_the_window_to_max_scale() -> None:
    path = camera_path(still_face(960, 5000), FRAME_W, FRAME_H, duration_ms=5000, zoom_at_ms=[500])
    holding = path.keyframes[75]  # 2500 ms: between 2000 and 3000, the hold

    assert (holding.w, holding.h) == (528, 940)
    assert (path.keyframes[0].w, path.keyframes[-1].w) == (608, 608)


# Step 6 · cut bridges


def test_each_cut_switches_between_100_and_110_percent() -> None:
    path = camera_path(
        still_face(960, 3000), FRAME_W, FRAME_H, duration_ms=3000, cut_at_ms=[1000, 2000]
    )
    widths = [keyframe.w for keyframe in path.keyframes]

    assert widths[29] == 608
    assert widths[30] == 552
    assert widths[59] == 552
    assert widths[60] == 608


def test_cut_between_face_samples_jumps_straight_to_the_new_face() -> None:
    # Old shot until 1700 ms, new shot from 1800 ms, cut at 1753 ms (frame 53, t=1767).
    faces = still_face(700, 1800) + [make_box(t, 1200) for t in range(1800, 3000, 100)]

    path = camera_path(faces, FRAME_W, FRAME_H, duration_ms=3000, cut_at_ms=[1753])

    assert center_x(path.keyframes[52]) == 700
    assert center_x(path.keyframes[53]) == 1200


def test_face_is_not_mixed_across_a_cut() -> None:
    faces = [make_box(1700, 700), make_box(1800, 1200)]

    before_cut = face_at(faces, 1733, cut_at_ms=[1767])
    after_cut = face_at(faces, 1767, cut_at_ms=[1767])

    assert before_cut == faces[0]
    assert after_cut == faces[1]


def test_camera_jumps_to_the_face_on_a_cut() -> None:
    faces = still_face(700, 1000) + [make_box(t, 1200) for t in range(1000, 2000, 100)]

    path = camera_path(faces, FRAME_W, FRAME_H, duration_ms=2000, cut_at_ms=[1000])

    assert center_x(path.keyframes[30]) == 1200


# Step 7 · keyframes and gaps


def test_one_keyframe_per_frame() -> None:
    path = camera_path(still_face(960, 1000), FRAME_W, FRAME_H, duration_ms=1000)

    assert len(path.keyframes) == 30
    assert [keyframe.t_ms for keyframe in path.keyframes[:3]] == [0, 33, 67]


def test_no_faces_at_all_centers_the_window() -> None:
    path = camera_path([], FRAME_W, FRAME_H, duration_ms=1000)

    assert {keyframe.x for keyframe in path.keyframes} == {(1920 - 608) // 2}


def test_face_is_interpolated_between_close_boxes() -> None:
    faces = [make_box(0, 150), make_box(100, 250)]

    face = face_at(faces, 50)

    assert face is not None
    assert face.x + face.w / 2 == 200


def test_face_is_held_across_a_gap() -> None:
    faces = [make_box(0, 500), make_box(3000, 1500)]

    face = face_at(faces, 1500)

    assert face == faces[0]


def test_gaps_longer_than_two_seconds_are_reported() -> None:
    faces = [make_box(0, 960), make_box(100, 960), make_box(3100, 960), make_box(4000, 960)]

    assert find_no_face_ranges(faces, duration_ms=4100) == [NoFaceRange(start_ms=100, end_ms=3100)]


def test_no_faces_at_all_is_one_long_gap() -> None:
    assert find_no_face_ranges([], duration_ms=5000) == [NoFaceRange(start_ms=0, end_ms=5000)]
