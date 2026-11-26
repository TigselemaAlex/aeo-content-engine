import pytest

from content_engine.piece_types.clip.domain.camera_path import CropKeyframe
from content_engine.piece_types.clip.domain.sendcmd import command_time_s, crop_commands


def window(frame: int, x: int, y: int = 0, w: int = 608, h: int = 1080) -> CropKeyframe:
    return CropKeyframe(t_ms=round(frame * 1000 / 30), x=x, y=y, w=w, h=h)


def test_command_lands_half_a_frame_before_its_frame() -> None:
    # Frame 2 starts at 0.0667 s; its keyframe says t_ms=67, which FFmpeg would only
    # reach on frame 3. Half a frame earlier, 0.05 s, is always before frame 2 and
    # after frame 1 (0.0333 s).
    assert command_time_s(0) == 0
    assert command_time_s(2) == pytest.approx(0.05)
    assert 1 / 30 < command_time_s(2) < 2 / 30


def test_first_frame_sets_every_value() -> None:
    text = crop_commands([window(0, x=820)])

    assert text == (
        "0.0000 [enter] crop@camera w 608, [enter] crop@camera h 1080, "
        "[enter] crop@camera x 820, [enter] crop@camera y 0;\n"
    )


def test_only_changed_values_are_sent() -> None:
    text = crop_commands([window(0, x=820), window(1, x=820), window(2, x=822)])

    lines = text.splitlines()
    assert len(lines) == 2
    assert lines[1] == "0.0500 [enter] crop@camera x 822;"


def test_bridge_sends_the_new_size_and_place_together() -> None:
    # Test stretch, cut at frame 96: 608 px at x 851 -> 552x982 bridge at x 946, y 49.
    keyframes = [window(frame, x=851) for frame in range(96)]
    keyframes.append(window(96, x=946, y=49, w=552, h=982))

    lines = crop_commands(keyframes).splitlines()

    assert len(lines) == 2
    assert lines[1] == (
        "3.1833 [enter] crop@camera w 552, [enter] crop@camera h 982, "
        "[enter] crop@camera x 946, [enter] crop@camera y 49;"
    )


def test_no_keyframes_gives_no_commands() -> None:
    assert crop_commands([]) == ""
