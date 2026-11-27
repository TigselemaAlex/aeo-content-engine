from content_engine.adapters.media.libass import parse_caption_boxes, parse_font_picks
from content_engine.piece_types.clip.domain.caption_checks import FontPick
from content_engine.piece_types.clip.domain.captions_ass import Box

# Lines as FFmpeg 9.0.2 printed them on 26 nov 2026 (Windows, gyan.dev build).
BBOX_LOG = "\n".join(
    [
        "[bbox@caption @ 000001d76eb9e300] n:0 pts:0 pts_time:0",
        "[bbox@highlight @ 000001d76eb9e400] n:0 pts:0 pts_time:0",
        "[bbox@caption @ 000001d76eb9e300] n:2 pts:2 pts_time:0.0666667 x1:322 x2:752"
        " y1:1603 y2:1684 w:431 h:82 crop=431:82:322:1603 drawbox=322:1603:431:82",
        "[bbox@highlight @ 000001d76eb9e400] n:2 pts:2 pts_time:0.0666667 x1:339 x2:428"
        " y1:1633 y2:1667 w:90 h:35 crop=90:35:339:1633 drawbox=339:1633:90:35",
    ]
)

FONT_LOG = "\n".join(
    [
        "[Parsed_ass_0 @ 00000150889aeec0] Loading font file 'fonts\\Figtree-Bold.ttf'",
        "[Parsed_ass_0 @ 00000150889aeec0] fontselect: (Figtree, 700, 0)"
        " -> Figtree-Bold, 0, Figtree-Bold",
        "[Parsed_ass_0 @ 000002d4ffb9fcc0] fontselect: (Figtreee, 700, 0)"
        " -> Arial-BoldMT, 0, Arial-BoldMT",
        "[Parsed_ass_0 @ 000002d4ffb9fcc0] fontselect: failed to find any fallback"
        " with glyph 0x1F600 for font: (Figtree, 700, 0)",
    ]
)


def test_boxes_are_read_per_frame_and_missing_frames_are_empty() -> None:
    frames = parse_caption_boxes(BBOX_LOG, frames=3)

    assert [f.frame for f in frames] == [0, 1, 2]
    assert frames[0].caption is None and frames[1].caption is None
    assert frames[2].caption == Box(x1=322, y1=1603, x2=752, y2=1684)
    assert frames[2].highlight == Box(x1=339, y1=1633, x2=428, y2=1667)


def test_font_picks_include_fallbacks_and_missing_glyphs() -> None:
    assert parse_font_picks(FONT_LOG) == [
        FontPick(requested="Figtree", chosen="Figtree-Bold"),
        FontPick(requested="Figtreee", chosen="Arial-BoldMT"),
        FontPick(requested="Figtree", chosen=None),
    ]
