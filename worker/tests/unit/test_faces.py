from content_engine.piece_types.clip.domain.faces import FaceBox, pick_main_face


def make_box(t_ms: int, x: int, y: int, w: int = 100, h: int = 100) -> FaceBox:
    return FaceBox(t_ms=t_ms, x=x, y=y, w=w, h=h, score=0.9)


def make_track(x: int, y: int, w: int, h: int, frames: int, start_ms: int = 0) -> list[FaceBox]:
    return [make_box(t_ms=start_ms + i * 100, x=x, y=y, w=w, h=h) for i in range(frames)]


def test_empty_input_returns_empty() -> None:
    assert pick_main_face([]) == []


def test_single_face_keeps_every_box() -> None:
    boxes = make_track(x=800, y=200, w=500, h=500, frames=10)

    assert pick_main_face(boxes=boxes) == boxes


def test_small_false_face_is_dropped() -> None:
    main = make_track(x=800, y=200, w=500, h=500, frames=20)
    false_face = make_track(x=100, y=100, w=600, h=600, frames=3)

    result = pick_main_face(boxes=main + false_face)

    assert result == main


def test_persistent_face_beats_brief_bigger_face() -> None:
    persistent = make_track(x=1200, y=300, w=300, h=300, frames=30)
    brief = make_track(x=100, y=100, w=600, h=600, frames=3)

    result = pick_main_face(boxes=persistent + brief)

    assert result == persistent


def test_bigger_face_wins_when_both_persist() -> None:
    big = make_track(x=1000, y=200, w=400, h=400, frames=10)
    small = make_track(x=100, y=200, w=200, h=200, frames=10)

    result = pick_main_face(boxes=small + big)

    assert result == big


def test_slow_movement_stays_one_track() -> None:
    boxes = [make_box(t_ms=i * 100, x=800 + i * 20, y=200, w=500, h=500) for i in range(20)]

    assert pick_main_face(boxes=boxes) == boxes


def test_face_returning_after_gap_rejoins_track() -> None:
    before = make_track(x=800, y=200, w=500, h=500, frames=10)
    after = make_track(x=800, y=200, w=500, h=500, frames=10, start_ms=5000)

    assert pick_main_face(before + after) == before + after


def test_jump_within_half_width_stays_in_track() -> None:
    first = make_track(0, 0, 100, 100, frames=5)
    shifted = make_track(40, 0, 100, 100, frames=3, start_ms=500)

    assert pick_main_face(first + shifted) == first + shifted


def test_jump_over_half_width_starts_new_track() -> None:
    first = make_track(0, 0, 100, 100, frames=5)
    shifted = make_track(60, 0, 100, 100, frames=3, start_ms=500)

    assert pick_main_face(first + shifted) == first


def test_center_uses_height() -> None:
    tall = make_track(0, 0, 100, 300, frames=5)
    square = make_track(0, 0, 100, 100, frames=3, start_ms=500)

    assert pick_main_face(tall + square) == tall


def test_same_frame_boxes_never_share_a_track() -> None:
    left = make_track(0, 0, 100, 100, frames=5)
    right = make_track(10, 0, 100, 100, frames=5)

    result = pick_main_face(left + right)

    times = [box.t_ms for box in result]
    assert len(times) == len(set(times))


def test_input_order_does_not_matter() -> None:
    boxes = make_track(800, 200, 500, 500, frames=10)

    assert pick_main_face(list(reversed(boxes))) == boxes
