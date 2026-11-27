"""Check the burned captions of a clip for `verify-clip` (docs/03 §5.4 and §5.7).

Pure code: the media adapter (`libass.py`) renders the ASS file alone with libass and
measures, on every frame, the box of the caption and the box of the highlighted word,
and reads which font libass picked. This module reads the ASS back and applies the
limits: font, words, sync, face and safe zone, the 5 checks that `--captions` adds to
the 10 of `verify_clip`. Boxes are pixels of the 1080x1920 output, inclusive on both
ends, as FFmpeg's `bbox` filter reports them; frames are frames of the clip at 30 fps;
times are clip milliseconds.
"""

import math
import re

from pydantic import BaseModel, ConfigDict

from content_engine.piece_types.clip.domain.camera_path import (
    CropKeyframe,
    cut_frame_starts_ms,
    face_at,
)
from content_engine.piece_types.clip.domain.captions_ass import (
    ORGANIC_SAFE_ZONE,
    Box,
    CaptionStyle,
    SafeZone,
    ass_override_color,
    caption_text,
    face_box_px,
    read_ass_style,
)
from content_engine.piece_types.clip.domain.faces import FaceBox
from content_engine.piece_types.clip.domain.ffmpeg_args import OUTPUT_H, OUTPUT_W
from content_engine.piece_types.clip.domain.timeline import Timeline
from content_engine.piece_types.clip.domain.verify import Check, frame_list
from content_engine.shared.transcript import Word

SWITCH_TOLERANCE = 0.02
"""How far, as a share of the caption width, the highlight must move to count as a new word.

More than 2 % of the caption width (docs/03 §5.7, row "Sincronía"). Measuring against
the caption box keeps the pop from counting: on the test stretch, while the first line
grows from 431 to 518 px, the highlight's left edge only goes from 3.9 % to 3.7 % of
the width; when "if" takes over from "And" it jumps to 28.8 %.
"""

COVER_MARGIN_PX = 2
"""Window pixels added around a caption box when it is left out of a frame comparison.

Covers the blur that scaling the window to 1080x1920 spreads around the captions
(docs/03 §5.7: "más 2 px de margen"). With the caption box left out, the worst frame of
the test stretch matches its window at 43.8 dB and the cut bridges land 9 of 9; without
it, 20.1 dB and 0 of 9.
"""

BOLD_NAMES = ("bold", "black", "heavy")
"""Words in a font's name that mark a bold face (Bold, SemiBold, ExtraBold, Black, Heavy).

When the style is bold and the font libass picked has none of them, libass would fake
the bold from the regular face, so the check fails (decided by Alex on 26 nov 2026,
docs/03 §5.4, row "Fuentes").
"""

_TAG_OR_TEXT = re.compile(r"\{([^}]*)\}|([^{]+)")
"""One override block in braces (group 1, without the braces) or a run of text (group 2)."""

_PRIMARY_COLOR = re.compile(r"\\1c(&H[0-9A-Fa-f]+&)")
"""The `1c` override tag that sets the text color, with its `&HBBGGRR&` color (group 1)."""


class CaptionFrame(BaseModel):
    """What libass drew on one frame, measured by `probe_captions`.

    Test stretch, frame 2 (the first line entering at 84 %): caption x 322-752 and
    y 1596-1677, highlight ("And") x 339-428 and y 1626-1661. Immutable.

    Attributes:
        frame: Index of the frame, from 0.
        caption: Box of everything drawn (the line and its box), in output pixels, or
            None if nothing.
        highlight: Box of the pixels in the highlight color, in output pixels, or None
            if none.
    """

    frame: int
    caption: Box | None
    highlight: Box | None

    model_config = ConfigDict(frozen=True)


class FontPick(BaseModel):
    """A font that libass looked for and the font it used.

    Read from the `fontselect` lines of libass's debug log (`parse_font_picks`). A
    missing font does not make libass fail: `(Figtreee, 700, 0) -> Arial-BoldMT` was
    measured on 26 nov 2026 (docs/03 §5.4, row "Fuentes"). Immutable.

    Attributes:
        requested: Family the ASS style asked for, such as `"Figtree"`.
        chosen: Name of the font libass used, such as `"Figtree-Bold"`, or None if it
            found none.
    """

    requested: str
    chosen: str | None

    model_config = ConfigDict(frozen=True)


class AssEvent(BaseModel):
    """One `Dialogue` of a captions file, read back by `read_ass_events`.

    Test stretch, first row: line 0, word 29, words `["And", "if", "your", "brand"]`,
    highlighted 0. Immutable.

    Attributes:
        line: Index of the line, from the Name field.
        word_i: Transcript index of the word being said, from the Name field.
        words: The words of the line, without tags.
        highlighted: Position in `words` of the word in the highlight color, or None
            when no word is (`highlight_mode` `none`, or a non-keyword in `keywords`).
    """

    line: int
    word_i: int
    words: list[str]
    highlighted: int | None

    model_config = ConfigDict(frozen=True)


def highlight_plane(style: CaptionStyle) -> tuple[str, int]:
    """Pick the color channel that tells the highlight apart, and the threshold on it.

    The channel is the one where the highlight color is furthest above both the text
    and the box colors; the threshold is halfway between the highlight and the
    brighter of the two others, rounded down. `probe_captions` keeps only the pixels at
    or above it on that channel, which gives the box of the word being said (docs/03
    §5.7).

    Args:
        style: The caption style, read from the ASS file (`read_ass_style`).

    Returns:
        The channel (`"r"`, `"g"` or `"b"`) and the threshold, 0 to 255.

    Raises:
        ValueError: If no channel of the highlight is above the text and the box.

    Example:
        White (255, 255, 255) over orange #FF7B2A (255, 123, 42) and black: red is
        255 against 255, green 255 against 123 and blue 255 against 42, so blue wins
        and (255 + 42) // 2 = 148.

        >>> highlight_plane(CaptionStyle())
        ('b', 148)
    """

    def channels(color: str) -> dict[str, int]:
        return {"r": int(color[1:3], 16), "g": int(color[3:5], 16), "b": int(color[5:7], 16)}

    highlight = channels(style.highlight_color)
    others = [channels(style.text_color), channels(style.box_color)]
    plane = max("rgb", key=lambda p: highlight[p] - max(other[p] for other in others))
    darker = max(other[plane] for other in others)
    if highlight[plane] <= darker:
        raise ValueError("the highlight color is not brighter than the text and box on any channel")
    return plane, (highlight[plane] + darker) // 2


def _font_key(name: str) -> str:
    """Return a font name without spaces or hyphens, in lower case ("figtreebold")."""
    return re.sub(r"[\s-]", "", name).lower()


def wrong_fonts(fonts: list[FontPick], style: CaptionStyle) -> list[FontPick]:
    """Return the picks that are not the style's font family, or not bold when it is bold.

    A pick is wrong when libass found no font, when it asked for another family than
    `style.font_name`, when the font it used is of another family (a fallback), or when
    the style is bold and the font's name has none of `BOLD_NAMES` (libass would fake
    the bold from a regular face). Names are compared without spaces, hyphens or case,
    so "Figtree-Bold" is family "figtree" plus "bold" (docs/03 §5.4, row "Fuentes").

    Args:
        fonts: The fonts libass looked for and used, from `parse_font_picks`.
        style: The caption style, read from the ASS file.

    Returns:
        The wrong picks, in their order; empty when every pick is right.

    Example:
        Arial is a fallback, Figtree-Regular is not bold and Phudu (a forbidden font
        of Guidepost) is not the style's family.

        >>> style = CaptionStyle()
        >>> [p.chosen for p in wrong_fonts([
        ...     FontPick(requested="Figtree", chosen="Figtree-Bold"),
        ...     FontPick(requested="Figtree", chosen="Arial-BoldMT"),
        ...     FontPick(requested="Figtree", chosen="Figtree-Regular"),
        ...     FontPick(requested="Phudu", chosen="Phudu-Bold"),
        ... ], style)]
        ['Arial-BoldMT', 'Figtree-Regular', 'Phudu-Bold']
    """
    family = _font_key(style.font_name)

    def right(pick: FontPick) -> bool:
        if pick.chosen is None or _font_key(pick.requested) != family:
            return False
        chosen = _font_key(pick.chosen)
        if not chosen.startswith(family):
            return False
        return not style.bold or any(word in chosen[len(family) :] for word in BOLD_NAMES)

    return [pick for pick in fonts if not right(pick)]


def check_fonts(fonts: list[FontPick], style: CaptionStyle) -> Check:
    """Check that libass drew every caption with the style's font and weight, no fallback.

    The `caption font` check of `verify-clip`, which `compose` also runs before burning
    the captions (`check_caption_fonts`). It fails when a pick is wrong (`wrong_fonts`)
    or when there is no pick at all, because then libass drew nothing. The value lists
    the fonts used, or the wrong picks as `requested -> chosen`.

    Args:
        fonts: The fonts libass looked for and used, from `parse_font_picks`.
        style: The caption style, read from the ASS file.

    Returns:
        The check, blocking.

    Example:
        Test stretch: one pick, Figtree -> Figtree-Bold, so the value is
        `Figtree-Bold` against the limit `only Figtree Bold`.

        >>> check = check_fonts([FontPick(requested="Figtree", chosen="Figtree-Bold")],
        ...                     CaptionStyle())
        >>> check.value, check.limit, check.ok
        ('Figtree-Bold', 'only Figtree Bold', True)
        >>> check_fonts([FontPick(requested="Figtreee", chosen="Arial-BoldMT")],
        ...             CaptionStyle()).value
        'Figtreee -> Arial-BoldMT'
    """
    wrong = wrong_fonts(fonts, style)
    chosen = sorted({pick.chosen or "none" for pick in fonts})
    value = ", ".join(chosen) if chosen else "nothing drawn"
    if wrong:
        value = ", ".join(f"{pick.requested} -> {pick.chosen}" for pick in wrong)
    weight = " Bold" if style.bold else ""
    return Check(
        name="caption font",
        value=value,
        limit=f"only {style.font_name}{weight}",
        ok=bool(fonts) and not wrong,
    )


def read_ass_events(ass_text: str, style: CaptionStyle) -> list[AssEvent]:
    """Read the `Dialogue` rows of a captions file written by `captions_ass`.

    The line index and the transcript index of the word come from the Name field
    (`<line>:<index>`). The text is read block by block: override tags are skipped,
    except the `1c` color, and each word is in the highlight color when the last `1c`
    before it is `style.highlight_color`. Words are split on plain spaces only:
    `caption_text` turns the inner spaces of a word into no-break spaces, which stay
    inside it.

    Args:
        ass_text: The whole text of a captions file.
        style: The caption style, read from the same file (`read_ass_style`).

    Returns:
        One event per `Dialogue` row, in file order.

    Example:
        Test stretch: 78 events. The first is line 0, word 29, words "And", "if",
        "your", "brand", highlighted 0; the second, word 30 with "if" (1) highlighted.
    """
    highlight = ass_override_color(style.highlight_color).upper()
    events: list[AssEvent] = []
    for row in ass_text.splitlines():
        if not row.startswith("Dialogue:"):
            continue
        fields = row.removeprefix("Dialogue:").strip().split(",", 9)
        line, word_i = (int(part) for part in fields[4].split(":"))
        color: str | None = None
        words: list[str] = []
        highlighted: int | None = None
        for tags, text in _TAG_OR_TEXT.findall(fields[9]):
            if tags:
                for found in _PRIMARY_COLOR.findall(tags):
                    color = found.upper()
                continue
            for word in (part for part in text.split(" ") if part):
                if color == highlight:
                    highlighted = len(words)
                words.append(word)
        events.append(AssEvent(line=line, word_i=word_i, words=words, highlighted=highlighted))
    return events


def _relative(caption: Box, highlight: Box) -> tuple[float, float]:
    """Return the left and right edges of the highlight as shares of the caption width.

    (highlight x1 - caption x1) / width and (highlight x2 + 1 - caption x1) / width,
    with width = caption x2 - caption x1 + 1. Test stretch, frame 4: "And" at x 300-407
    in a caption at x 281-798 (518 px) gives 19 / 518 = 0.037 and 127 / 518 = 0.245.
    """
    width = caption.x2 - caption.x1 + 1
    return (highlight.x1 - caption.x1) / width, (highlight.x2 + 1 - caption.x1) / width


def highlight_switches(
    frames: list[CaptionFrame], tolerance: float = SWITCH_TOLERANCE
) -> list[int]:
    """Return the frames where a new word turns to the highlight color.

    The highlight is compared with the caption box it sits in, so the "pop" (the whole
    line growing) does not count. A new word starts where the highlight appears, where
    it moves by more than `tolerance` of the caption width, where the caption box
    shrinks (a new line enters small), or where the caption box changes after staying
    still for a frame (a new line, with or without the pop). Two lines in a row that
    draw exactly the same box and the same highlight cannot be told apart (docs/03
    §5.7, row "Sincronía").

    Args:
        frames: What libass drew on each frame, in frame order, from `probe_captions`.
        tolerance: Smallest move of an edge of the highlight, as a share of the caption
            width, that counts. `SWITCH_TOLERANCE` (2 %) by default.

    Returns:
        The frames where a word starts being highlighted, in order.

    Example:
        Test stretch: 78 switches for 78 words, starting [2, 11, 14, 19, 45, ...].
        Frame 2: the highlight appears. Frames 3 and 4: the pop grows the caption from
        431 to 477 and 518 px, but the highlight's left edge stays at 3.8 % and 3.7 %
        of the width: no switch. Frame 11: "if" takes over and the left edge moves from
        3.7 % to 28.8 %. Frame 45: "isn't in that answer," enters at 84 % and the caption
        shrinks from 56980 to 40504 px.
    """
    switches: list[int] = []
    for k, frame in enumerate(frames):
        caption, highlight = frame.caption, frame.highlight
        if caption is None or highlight is None:
            continue
        previous = frames[k - 1] if k > 0 else None
        if previous is None or previous.caption is None or previous.highlight is None:
            switches.append(frame.frame)
            continue
        before = _relative(previous.caption, previous.highlight)
        now = _relative(caption, highlight)
        moved = max(abs(before[0] - now[0]), abs(before[1] - now[1])) > tolerance
        shrank = caption.area < previous.caption.area
        still_before = k > 1 and frames[k - 2].caption == previous.caption
        changed_after_still = caption != previous.caption and still_before
        if moved or shrank or changed_after_still:
            switches.append(frame.frame)
    return switches


def window_cover(
    box: Box, window: CropKeyframe, margin: int = COVER_MARGIN_PX
) -> tuple[int, int, int, int]:
    """Return the pixels of a crop window that a caption box covers, as slice bounds.

    The box is in output pixels (1080x1920); the window was scaled up to that size, so
    the box shrinks back by window size / output size, rounded outwards, and grows
    `margin` pixels on each side for the blur of the scaling. The bounds are clipped to
    the window. `match_frames` leaves these pixels out when it compares a clip frame
    with the mezzanine, which has no captions (docs/03 §5.7).

    Args:
        box: The caption box of the frame, in output pixels, both ends included.
        window: The crop window of the frame; only its size is used.
        margin: Window pixels added on each side. `COVER_MARGIN_PX` (2) by default.

    Returns:
        `(x1, y1, x2, y2)` in window pixels, with `x2` and `y2` excluded.

    Example:
        Test stretch, frame 4: caption x 281-798, y 1587-1696, window 608x1080, so
        x scales by 608 / 1080 = 0.563 and y by 1080 / 1920 = 0.5625.
        x1 = floor(281 x 0.563) - 2 = 158 - 2 = 156, y1 = floor(1587 x 0.5625) - 2 =
        892 - 2 = 890, x2 = ceil(799 x 0.563) + 2 = 450 + 2 = 452 and y2 =
        ceil(1697 x 0.5625) + 2 = 955 + 2 = 957: 296 x 67 px, 3 % of the window.

        >>> caption = Box(x1=281, y1=1587, x2=798, y2=1696)
        >>> window_cover(caption, CropKeyframe(t_ms=133, x=820, y=0, w=608, h=1080))
        (156, 890, 452, 957)
    """
    scale_x = window.w / OUTPUT_W
    scale_y = window.h / OUTPUT_H
    return (
        max(0, math.floor(box.x1 * scale_x) - margin),
        max(0, math.floor(box.y1 * scale_y) - margin),
        min(window.w, math.ceil((box.x2 + 1) * scale_x) + margin),
        min(window.h, math.ceil((box.y2 + 1) * scale_y) + margin),
    )


def box_gap(a: Box, b: Box) -> float:
    """Return the space between two boxes in pixels: negative when they overlap.

    The widest of the four gaps (left, right, above, below), minus 1 because `Box`
    includes both ends: two boxes that touch have 0 px between them. Test stretch: the
    caption box comes as close as 19 px to the face (docs/03 §5.7).

    Args:
        a: One box, in output pixels.
        b: The other box, in output pixels.

    Returns:
        The free pixels between the boxes; 0 when they touch, negative when they overlap.

    Example:
        Rows 100 to 119 lie between a box ending on row 99 and one starting on row 120:
        120 - 99 - 1 = 20 px.

        >>> a = Box(x1=0, y1=0, x2=99, y2=99)
        >>> box_gap(a, Box(x1=0, y1=120, x2=99, y2=199))
        20.0
        >>> box_gap(a, Box(x1=0, y1=100, x2=99, y2=199))
        0.0
    """
    return max(a.x1 - b.x2, b.x1 - a.x2, a.y1 - b.y2, b.y1 - a.y2) - 1


def check_captions(
    ass_text: str,
    words: list[Word],
    timeline: Timeline,
    frames: list[CaptionFrame],
    fonts: list[FontPick],
    keyframes: list[CropKeyframe],
    faces: list[FaceBox],
    cut_frames: list[int],
    safe_zone: SafeZone = ORGANIC_SAFE_ZONE,
    fps: int = 30,
) -> list[Check]:
    """Check the captions of a clip: font, words, sync, face and safe zone, in this order.

    The style comes from the ASS file itself (`read_ass_style`). The expected words are
    the words of the clip's range that are not fillers and have something to show, and
    their times come from the timeline's time map, not from the code that wrote the
    captions (docs/03 §5.7). Returns five checks (approved by Alex on 26 nov 2026):

    1. `caption font`: libass used only the style's family, in bold if the style is
       bold, and no fallback (`check_fonts`).
    2. `caption words`: the lines show exactly the expected words, in order, and no
       event is about a word outside them.
    3. `caption sync`: each word turns to the highlight color at most half a frame,
       1000 / 30 / 2 = 16.7 ms, from its start in the clip (`highlight_switches`).
    4. `captions clear of face`: on no frame does the caption box overlap the face box.
    5. `captions in safe zone`: the caption box stays inside `safe_zone`. Only a
       warning (`blocking=False`): below the face of a close-up it cannot (docs/03
       §5.4, step 5).

    Args:
        ass_text: The whole text of the captions file.
        words: Transcript words of the clip's range, such as
            `transcript.words[from_word : to_word + 1]`.
        timeline: The clip's cuts, from `build_timeline`.
        frames: What libass drew on each frame, from `probe_captions`.
        fonts: The fonts libass picked, from `probe_captions`.
        keyframes: The camera path the clip was made with, one keyframe per frame.
        faces: Boxes of the main face, in mezzanine pixels, sorted by `t_ms`.
        cut_frames: Frames of the cuts, from `cut_at_frames`.
        safe_zone: Margins of the platform buttons. `ORGANIC_SAFE_ZONE` by default.
        fps: Frame rate of the clip. 30 by default (docs/03 §5.6).

    Returns:
        The five checks. The captions pass if the four blocking ones are `ok`.

    Raises:
        ValueError: If the file has no `Style: Caption,...` line (`read_ass_style`).

    Example:
        Test stretch (words 29 to 108): `Figtree-Bold`; 78 shown of 78; 78 words, worst
        16.7 ms; 0 frames over the face, closest 19 px; and the warning: 1002 frames
        outside the safe zone, lowest edge at 1809 px (docs/03 §5.7).
    """
    style = read_ass_style(ass_text)
    events = read_ass_events(ass_text, style)
    expected = [word for word in words if not word.is_disfluency and caption_text(word.text)]
    return [
        check_fonts(fonts, style),
        _words_check(events, expected),
        _sync_check(events, expected, timeline, frames, fps),
        _face_check(frames, keyframes, faces, cut_frames),
        _safe_zone_check(frames, safe_zone),
    ]


def _words_check(events: list[AssEvent], expected: list[Word]) -> Check:
    """Check that the lines show exactly the expected words, in order, and nothing else.

    Each line is counted once, from its first event. The value says how many words were
    shown, then either the events about words outside the clip (the first 8) or the
    position of the first word that differs.
    """
    shown: list[str] = []
    seen_lines: set[int] = set()
    for event in events:
        if event.line not in seen_lines:
            seen_lines.add(event.line)
            shown.extend(event.words)
    texts = [caption_text(word.text) for word in expected]
    foreign = sorted({event.word_i for event in events} - {word.i for word in expected})
    ok = shown == texts and not foreign
    value = f"{len(shown)} shown of {len(texts)}"
    if foreign:
        value += f"; {len(foreign)} not in the clip ({', '.join(map(str, foreign[:8]))})"
    elif not ok:
        first = next(
            (k for k, (a, b) in enumerate(zip(shown, texts, strict=False)) if a != b),
            min(len(shown), len(texts)),
        )
        value += f"; first difference at word {first}"
    return Check(name="caption words", value=value, limit="the clip's words, in order", ok=ok)


def _sync_check(
    events: list[AssEvent],
    expected: list[Word],
    timeline: Timeline,
    frames: list[CaptionFrame],
    fps: int,
) -> Check:
    """Check that each word turns to the highlight color on the frame nearest its start.

    The n-th highlight switch (`highlight_switches`) is paired with the n-th highlighted
    event, and its offset is frame x 1000 / 30 - word start, in clip milliseconds. The
    limit is half a frame, 1000 / 30 / 2 = 16.7 ms; the extra 1e-9 ms absorbs floating
    point noise: on the test stretch "the" (17050 ms) and "a" (24150 ms) start exactly
    between two frames and measure 16.66666666666788 ms. It passes with no highlighted
    word and no switch (`highlight_mode` `none`), and fails when the counts differ.
    """
    start_ms = {
        word.i: clip_ms
        for word in expected
        if (clip_ms := timeline.to_clip_ms(word.start_ms)) is not None
    }
    highlighted = [event.word_i for event in events if event.highlighted is not None]
    switches = highlight_switches(frames)
    limit_ms = 1000 / fps / 2
    limit = f"<= {limit_ms:.1f} ms (half a frame)"
    if not highlighted and not switches:
        return Check(name="caption sync", value="no highlighted words", limit=limit, ok=True)
    if len(switches) != len(highlighted) or any(i not in start_ms for i in highlighted):
        return Check(
            name="caption sync",
            value=f"{len(switches)} highlight changes for {len(highlighted)} words",
            limit=limit,
            ok=False,
        )
    offsets = [
        frame * 1000 / fps - start_ms[i] for frame, i in zip(switches, highlighted, strict=True)
    ]
    worst = max(abs(offset) for offset in offsets)
    return Check(
        name="caption sync",
        value=f"{len(offsets)} words; worst {worst:.1f} ms",
        limit=limit,
        ok=worst <= limit_ms + 1e-9,
    )


def _face_check(
    frames: list[CaptionFrame],
    keyframes: list[CropKeyframe],
    faces: list[FaceBox],
    cut_frames: list[int],
) -> Check:
    """Check that the caption box never overlaps the face box on any frame.

    The face of each frame comes from `face_at`, scaled to the output (`face_box_px`),
    and the gap from `box_gap`. The value lists the frames over the face and the
    closest gap; frames without captions or without a face are not compared.
    """
    cut_ms = cut_frame_starts_ms(cut_frames)
    over: list[int] = []
    closest: float | None = None
    for frame in frames:
        if frame.caption is None or frame.frame >= len(keyframes):
            continue
        keyframe = keyframes[frame.frame]
        face = face_at(faces, keyframe.t_ms, cut_ms)
        if face is None:
            continue
        gap = box_gap(frame.caption, face_box_px(keyframe, face))
        closest = gap if closest is None else min(closest, gap)
        if gap < 0:
            over.append(frame.frame)
    return Check(
        name="captions clear of face",
        value=f"{frame_list(over)} over the face; closest {closest:.0f} px"
        if closest is not None
        else "no frame with captions and a face",
        limit="0 frames",
        ok=not over,
    )


def _safe_zone_check(frames: list[CaptionFrame], safe_zone: SafeZone) -> Check:
    """Report the frames whose caption box leaves the platform safe zone (a warning only).

    With `ORGANIC_SAFE_ZONE` the box must stay within x 65-888 and y 160-1520. The value
    also gives the lowest bottom edge reached, in output pixels.
    """
    left, top = safe_zone.left, safe_zone.top
    right, bottom = OUTPUT_W - safe_zone.right, OUTPUT_H - safe_zone.bottom
    outside: list[int] = []
    lowest = 0.0
    for frame in frames:
        box = frame.caption
        if box is None:
            continue
        lowest = max(lowest, box.y2 + 1)
        if box.x1 < left or box.y1 < top or box.x2 + 1 > right or box.y2 + 1 > bottom:
            outside.append(frame.frame)
    return Check(
        name="captions in safe zone",
        value=f"{frame_list(outside)} outside; lowest edge {lowest:.0f} px",
        limit=f"x {left}-{right}, y {top}-{bottom} px",
        ok=not outside,
        blocking=False,
    )
