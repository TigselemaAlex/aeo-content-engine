"""Word-by-word captions of a clip, written as an ASS subtitle file (docs/03 §5.4).

Pure code: it picks the words the clip plays, groups them into lines, places each line
below the face and writes the ASS text; the media adapter burns it with FFmpeg and libass
(`libass.py` and `compose_clip`). Word times are clip milliseconds from the audio time
map of `Timeline`, so the captions follow the voice also across J cuts. Frames are frames
of the clip at 30 fps, the same as the mezzanine's. Positions and sizes are pixels of the
1080x1920 output, where libass draws (`PlayResX` and `PlayResY` of the file).
"""

import math
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from content_engine.piece_types.clip.domain.camera_path import CropKeyframe, face_at
from content_engine.piece_types.clip.domain.faces import FaceBox
from content_engine.piece_types.clip.domain.ffmpeg_args import OUTPUT_H, OUTPUT_W
from content_engine.piece_types.clip.domain.sendcmd import command_time_s
from content_engine.piece_types.clip.domain.timeline import Timeline, ms_to_frame
from content_engine.shared.transcript import Word

HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]
"""A color written as `#RRGGBB`: `#` and six hexadecimal digits, in either case."""

SENTENCE_BREAK = re.compile(r"[.,!?;:…]['\"”’)\]]*$")
"""Punctuation at the end of a word that closes a caption phrase (docs/03 §5.4, step 2).

One of `. , ! ? ; :` or `…`, optionally followed by closing quotes or brackets, as in
`answer,` or `exist.”`.
"""

STYLE_NAME = "Caption"
"""Name of the only ASS style of the captions; `read_ass_style` finds its line by it."""

NO_BREAK_SPACE = " "
"""No-break space (U+00A0) that keeps a word with an inner space ("10 000") as one word.

`read_ass_events` splits a line into words on plain spaces only, so the word stays whole.
"""


class SafeZone(BaseModel):
    """Margins of the vertical frame that the platform buttons and texts may cover.

    In pixels of the 1080x1920 output. A caption box that enters a margin only makes
    `verify-clip` warn, it never fails it (docs/03 §5.4, step 5, and §5.7). Immutable.

    Attributes:
        top: Pixels from the top edge, 0 or more.
        bottom: Pixels from the bottom edge, 0 or more.
        left: Pixels from the left edge, 0 or more.
        right: Pixels from the right edge, 0 or more.
    """

    top: int = Field(ge=0)
    bottom: int = Field(ge=0)
    left: int = Field(ge=0)
    right: int = Field(ge=0)

    model_config = ConfigDict(frozen=True)


ORGANIC_SAFE_ZONE = SafeZone(top=160, bottom=400, left=65, right=192)
"""Safe zone for organic posts on TikTok, Reels and Shorts, in 1080x1920 pixels.

Top 160, bottom 400, left 65 and right 192 px (docs/03 §5.4, step 6). There are no
official numbers for organic posts, only for ads (Google Shorts: top 288, bottom 672,
left 48, right 192; Meta Reels: 14 % top, 35 % bottom, 6 % on the sides); unofficial
guides give bottom 320-400, top 110-250 and right 120-192 (docs/00, "Subtítulos palabra
por palabra"). The right margin also sets the usable caption width, centered on x = 540:
2 x (1080 - 192 - 540) = 696 px (`CaptionStyle.max_chars_per_line`). Inside the zone, a
caption box spans x 65-888 and y 160-1520.
"""


class CaptionStyle(BaseModel):
    """How the captions look: the `captions` area of the Edit Spec (docs/03 §2.3).

    In Phase 0 the style is fixed here, with the defaults of Guidepost chosen by Alex on
    real frames of the test stretch (docs/03 §2.3 and §5.4); the Edit Spec feeds it from
    Phase 1. `bold`, `box_padding_px`, `pop_from`, `pop_ms` and `face_gap_px` are not
    Edit Spec parameters yet. Immutable.

    Attributes:
        font_name: Font family, as the font file names it and libass looks it up.
            Figtree, from Guidepost's Edit Spec; its file is `assets/fonts/Figtree-Bold.ttf`
            (docs/03 §5.4, row "Fuentes").
        bold: Whether the bold face is used. True: Figtree Bold (docs/03 §2.3).
        size_px: Font size, in output pixels, above 0. 72 (docs/03 §2.3); ExtraBold 80
            in capitals was dropped because 'ANSWER ENGINE OPTIMIZATION.' is wider than
            1080 px (docs/03 §5.4).
        text_color: Color of the words. #FF7B2A, Guidepost's `text_color` (docs/03 §2.3).
        highlight_color: Color of the word being said. #FFFFFF (docs/03 §5.4, step 4).
        box_color: Color of the box behind the line. #000000, Guidepost's
            `background.color` (docs/03 §2.3).
        box_padding_px: Space between the text and the edge of the box, in output pixels,
            0 or more. 18 (docs/03 §5.4, step 4).
        max_words_per_line: Most words on one line, 1 or more. 4 (docs/03 §2.3).
        max_chars_per_line: Most characters on one line, spaces included, 1 or more. 22:
            in Figtree Bold 72, 'Answer Engine Optimization.' (27 characters) measures
            840 px, about 840 / 27 = 31 px per character, and the usable width centered
            on x = 540 without the column of buttons on the right is 2 x (888 - 540) =
            696 px (docs/03 §5.4, step 2). 22 characters take about 22 x 31.1 = 684 px.
        highlight_mode: `word` highlights every word while it is said (Guidepost),
            `keywords` only the transcript indices given to `captions_ass` (for T2.6),
            `none` nothing.
        pop_from: Scale a line enters with, above 0 and up to 1. 0.80: the "pop" entrance
            from 80 % to 100 % (docs/03 §5.4).
        pop_ms: How long the line takes to grow from `pop_from` to full size, in
            milliseconds, 0 or more. 80 (docs/03 §5.4).
        face_gap_px: Space between the bottom of the face box and the top of the caption
            box, in output pixels, 0 or more. 20: "20 px below the chin" (docs/03 §5.4).
    """

    font_name: str = "Figtree"
    bold: bool = True
    size_px: int = Field(default=72, gt=0)
    text_color: HexColor = "#FF7B2A"
    highlight_color: HexColor = "#FFFFFF"
    box_color: HexColor = "#000000"
    box_padding_px: int = Field(default=18, ge=0)
    max_words_per_line: int = Field(default=4, ge=1)
    max_chars_per_line: int = Field(default=22, ge=1)
    highlight_mode: Literal["word", "keywords", "none"] = "word"
    pop_from: float = Field(default=0.80, gt=0, le=1)
    pop_ms: int = Field(default=80, ge=0)
    face_gap_px: int = Field(default=20, ge=0)

    model_config = ConfigDict(frozen=True)

    @property
    def box_height_px(self) -> int:
        """Height of the box of one line, in output pixels: size + 2 x padding.

        The font size plus the padding above and below the text. With the defaults,
        72 + 2 x 18 = 108 px, so the center of a box sits 108 // 2 = 54 px below its top.

        >>> CaptionStyle().box_height_px
        108
        """
        return self.size_px + 2 * self.box_padding_px


class Box(BaseModel):
    """A rectangle in output pixels, both ends included, as FFmpeg's `bbox` filter reports it.

    Holds the caption box and the highlight box that libass draws, and the face box
    scaled to the output (`face_box_px`). Coordinates are floats because a face box
    scaled from the mezzanine falls between pixels. Immutable.

    Attributes:
        x1: Left column.
        y1: Top row.
        x2: Right column, included.
        y2: Bottom row, included.
    """

    x1: float
    y1: float
    x2: float
    y2: float

    model_config = ConfigDict(frozen=True)

    @property
    def area(self) -> float:
        """Number of pixels inside the box: (x2 - x1 + 1) x (y2 - y1 + 1), both ends included.

        Test stretch, frame 4: the first line at full size spans x 281-798 and
        y 1587-1696, so 518 x 110 = 56980 px.

        >>> Box(x1=281, y1=1587, x2=798, y2=1696).area
        56980.0
        """
        return (self.x2 - self.x1 + 1) * (self.y2 - self.y1 + 1)


class ClipWord(BaseModel):
    """A transcript word that the clip keeps, with its times on the clip's clock.

    Built by `words_in_clip`. Immutable.

    Attributes:
        i: Index of the word in the transcript, 0 or more.
        text: The word as transcribed, punctuation included.
        start_ms: Where the word starts in the clip, in milliseconds, 0 or more.
        end_ms: Where the word ends in the clip, in milliseconds, 0 or more.
        cut: Index in `Timeline.cuts` of the audio cut the word plays in, 0 or more.
            Two words in different cuts never share a line (`split_into_phrases`).
    """

    i: int = Field(ge=0)
    text: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    cut: int = Field(ge=0)

    model_config = ConfigDict(frozen=True)


class CaptionLine(BaseModel):
    """One group of words, shown as a single line while its words are said.

    Test stretch: the first line is "And if your brand", shown on frames 2 to 44 with its
    center at y = 1642. Immutable.

    Attributes:
        words: The words of the line, in order.
        start_frame: First frame that shows the line, 0 or more.
        end_frame: First frame after the line, which no longer shows it, 0 or more.
        center_y: Vertical center of the line's box, in output pixels (`line_center_y`).
    """

    words: list[ClipWord]
    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)
    center_y: int

    model_config = ConfigDict(frozen=True)


class CaptionEvent(BaseModel):
    """One state of a line: which of its words is being said, and on which frames.

    Each event becomes one `Dialogue` row of the ASS file. Test stretch: "if", the
    second word of the first line, is said on frames 11 to 13. Immutable.

    Attributes:
        line: Index of the line in `CaptionPlan.lines`, 0 or more.
        word: Position, inside the line, of the word being said, 0 or more.
        start_frame: First frame of this state, 0 or more.
        end_frame: First frame after this state, 0 or more.
    """

    line: int = Field(ge=0)
    word: int = Field(ge=0)
    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)

    model_config = ConfigDict(frozen=True)


class CaptionPlan(BaseModel):
    """Everything the ASS file says, before it is written as text.

    Built by `plan_captions` and written by `captions_ass`. Test stretch: 27 lines,
    78 events and no skipped word. Immutable.

    Attributes:
        lines: The lines, in the order they are shown.
        events: The states of the lines, in time order, back to back.
        skipped: Transcript indices of words that never get a frame of their own,
            because the next word starts on the same frame. They are still shown in
            their line, but never highlighted.
    """

    lines: list[CaptionLine]
    events: list[CaptionEvent]
    skipped: list[int]

    model_config = ConfigDict(frozen=True)


def caption_text(text: str) -> str:
    """Return a word as the captions show it.

    Braces and backslashes are removed, because ASS reads them as override tags, and
    the spaces around the word are trimmed. Inner spaces become one `NO_BREAK_SPACE`
    each, so the word stays one word. An empty result means the word has nothing to
    show, and `words_in_clip` drops it.

    Args:
        text: The word as transcribed (`Word.text`).

    Returns:
        The text to draw, possibly empty.

    Example:
        >>> caption_text("{Hello}")
        'Hello'
        >>> caption_text("10 000") == "10" + NO_BREAK_SPACE + "000"
        True
        >>> caption_text("{}")
        ''
    """
    return re.sub(r"\s+", NO_BREAK_SPACE, re.sub(r"[{}\\]", "", text).strip())


def words_in_clip(words: list[Word], timeline: Timeline) -> list[ClipWord]:
    """Return the words the clip keeps, on the clip's clock, in play order.

    A word is kept when it is not a filler, it has something to show (`caption_text`)
    and it lies whole inside one audio cut: `Timeline.locate` finds its start and its
    end in the same cut (docs/03 §5.4, step 1). Its clip times come from the audio time
    map, so a word after a J cut is highlighted with the voice, before the image
    changes. The words are sorted by their clip start, which is not the transcript
    order when a hook plays first.

    Args:
        words: Transcript words of the clip's range, such as
            `transcript.words[from_word : to_word + 1]`.
        timeline: The clip's cuts, from `build_timeline`.

    Returns:
        One `ClipWord` per kept word, sorted by `start_ms`.

    Example:
        Test stretch (words 29 to 108): the 80 words give 78; the fillers 'um,' (37)
        and 'uh' (80) are dropped. "if" starts at 27020 ms of the original, inside the
        first audio cut (26655-29728 ms), so it starts at 27020 - 26655 = 365 ms of the
        clip. "you" (38), after the removed 'um,', starts at 30974 ms, 60 ms into the
        second cut, which starts at 3073 ms of the clip: 3073 + 60 = 3133 ms. It is
        highlighted on frame 94 and the image changes on frame 96.

        >>> from content_engine.piece_types.clip.domain.timeline import Cut
        >>> cut = Cut(start_ms=26655, end_ms=29728)
        >>> timeline = Timeline(cuts=[cut], video_cuts=[cut])
        >>> word = Word(
        ...     i=30, text="if", start_ms=27020, end_ms=27117,
        ...     speaker="A", confidence=1.0, is_disfluency=False,
        ... )
        >>> words_in_clip([word], timeline)
        [ClipWord(i=30, text='if', start_ms=365, end_ms=462, cut=0)]
    """
    kept: list[ClipWord] = []
    for word in words:
        if word.is_disfluency or not caption_text(word.text):
            continue
        start, end = timeline.locate(word.start_ms), timeline.locate(word.end_ms)
        if start is None or end is None or start[0] != end[0]:
            continue
        kept.append(
            ClipWord(i=word.i, text=word.text, start_ms=start[1], end_ms=end[1], cut=start[0])
        )
    return sorted(kept, key=lambda word: word.start_ms)


def line_text(words: list[ClipWord]) -> str:
    """Return the text of a line: its words, as `caption_text` shows them, joined by spaces.

    Its length is what `max_chars_per_line` limits, spaces included.

    >>> line_text([ClipWord(i=38, text="you", start_ms=3133, end_ms=3230, cut=1)])
    'you'
    """
    return " ".join(caption_text(word.text) for word in words)


def split_into_phrases(words: list[ClipWord], pause_max_ms: int = 500) -> list[list[ClipWord]]:
    """Split the words into phrases that a caption line never crosses.

    A phrase ends after a word with closing punctuation (`SENTENCE_BREAK`), where the
    next word plays in another audio cut (a filler or a long pause was removed between
    them), or where the silence before the next word is longer than `pause_max_ms`
    (docs/03 §5.4, step 2). The last word always closes a phrase.

    Args:
        words: The clip's words in play order, from `words_in_clip`.
        pause_max_ms: Longest silence inside a phrase, in clip milliseconds. 500 by
            default, the Edit Spec's `pacing.pause_max_ms` (docs/03 §2.3).

    Returns:
        The phrases, in order; together they hold every word once.

    Example:
        Test stretch: the 78 words make 16 phrases. The first two are "And if your
        brand isn't in that answer," and "you basically don't exist.", each closed by
        its punctuation; "you" also starts a new audio cut, because the filler 'um,'
        was cut out before it.
    """
    phrases: list[list[ClipWord]] = []
    current: list[ClipWord] = []
    for k, word in enumerate(words):
        current.append(word)
        following = words[k + 1] if k + 1 < len(words) else None
        if (
            following is None
            or SENTENCE_BREAK.search(word.text)
            or following.cut != word.cut
            or following.start_ms - word.end_ms > pause_max_ms
        ):
            phrases.append(current)
            current = []
    return phrases


def split_phrase(phrase: list[ClipWord], max_words: int, max_chars: int) -> list[list[ClipWord]]:
    """Split a phrase into the fewest lines that fit, with lengths as even as possible.

    Each line has at most `max_words` words and `max_chars` characters (`line_text`,
    spaces included); a single word longer than `max_chars` gets a line of its own.
    Every way to split the phrase is weighed at once, word by word (dynamic
    programming): fewer lines win, and among the splits with the fewest lines, the one
    whose longest line is shortest (docs/03 §5.4, step 2). The words keep their order.

    Args:
        phrase: The words of one phrase, from `split_into_phrases`.
        max_words: Most words on a line (`CaptionStyle.max_words_per_line`).
        max_chars: Most characters on a line (`CaptionStyle.max_chars_per_line`).

    Returns:
        The lines, in order; empty for an empty phrase.

    Example:
        Test stretch: "you basically don't exist." has 26 characters, more than 22, so
        it needs two lines. The two-line splits measure 3 + 22 ("you" / "basically
        don't exist."), 13 + 12 and 19 + 6 characters; the longest lines are 22, 13 and
        19, so 13 + 12 wins.

        >>> words = [
        ...     ClipWord(i=38 + k, text=text, start_ms=0, end_ms=0, cut=1)
        ...     for k, text in enumerate("you basically don't exist.".split())
        ... ]
        >>> [line_text(line) for line in split_phrase(words, max_words=4, max_chars=22)]
        ['you basically', "don't exist."]
    """
    count = len(phrase)
    best: list[tuple[int, int] | None] = [None] * (count + 1)
    best[0] = (0, 0)
    line_start = [0] * (count + 1)
    for end in range(1, count + 1):
        for start in range(end - 1, -1, -1):
            words = end - start
            if words > max_words:
                break
            chars = len(line_text(phrase[start:end]))
            if chars > max_chars and words > 1:
                break
            previous = best[start]
            if previous is None:
                continue
            candidate = (previous[0] + 1, max(previous[1], chars))
            current = best[end]
            if current is None or candidate < current:
                best[end] = candidate
                line_start[end] = start
    lines: list[list[ClipWord]] = []
    end = count
    while end > 0:
        lines.append(phrase[line_start[end] : end])
        end = line_start[end]
    return lines[::-1]


def group_words(
    words: list[ClipWord], style: CaptionStyle, pause_max_ms: int = 500
) -> list[list[ClipWord]]:
    """Group the clip's words into caption lines: phrases first, then lines that fit.

    `split_into_phrases` cuts at punctuation, audio cuts and long pauses, and
    `split_phrase` splits each phrase with the style's word and character limits.

    Args:
        words: The clip's words in play order, from `words_in_clip`.
        style: The caption style; only its two line limits are used.
        pause_max_ms: Longest silence inside a phrase, in clip milliseconds. 500 by
            default, the Edit Spec's `pacing.pause_max_ms` (docs/03 §2.3).

    Returns:
        The lines, in order; together they hold every word once.

    Example:
        Test stretch: 78 words in 27 lines, the first three "And if your brand",
        "isn't in that answer," and "you basically".
    """
    return [
        line
        for phrase in split_into_phrases(words, pause_max_ms)
        for line in split_phrase(phrase, style.max_words_per_line, style.max_chars_per_line)
    ]


def face_box_px(keyframe: CropKeyframe, face: FaceBox) -> Box:
    """Return a face box of the mezzanine in pixels of the output frame.

    The crop window `keyframe` is scaled up to 1080x1920, so a mezzanine point moves to
    (x - window x) x 1080 / window width and (y - window y) x 1920 / window height. The
    right and bottom edges are the first pixel past the face, minus 1, because `Box`
    includes both ends. Parts of the face outside the window fall outside 0-1079 or
    0-1919; they are not clipped.

    Args:
        keyframe: The crop window of the frame, in mezzanine pixels.
        face: The face box on that frame, in mezzanine pixels (`face_at`).

    Returns:
        The face box in output pixels.

    Example:
        Test stretch, frame 0: window 608x1080 at x 820, first face box at x 849,
        y 225, 549x549 px. x1 = (849 - 820) x 1080 / 608 = 51.5, y1 = 225 x 1920 /
        1080 = 400, x2 = (849 + 549 - 820) x 1080 / 608 - 1 = 1025.7 and y2 =
        (225 + 549) x 1920 / 1080 - 1 = 1375.

        >>> window = CropKeyframe(t_ms=0, x=820, y=0, w=608, h=1080)
        >>> face = FaceBox(t_ms=0, x=849, y=225, w=549, h=549, score=0.97)
        >>> box = face_box_px(window, face)
        >>> round(box.x1, 1), box.y1, round(box.x2, 1), box.y2
        (51.5, 400.0, 1025.7, 1375.0)
    """
    scale_x = OUTPUT_W / keyframe.w
    scale_y = OUTPUT_H / keyframe.h
    return Box(
        x1=(face.x - keyframe.x) * scale_x,
        y1=(face.y - keyframe.y) * scale_y,
        x2=(face.x + face.w - keyframe.x) * scale_x - 1,
        y2=(face.y + face.h - keyframe.y) * scale_y - 1,
    )


def face_bottom_px(keyframe: CropKeyframe, face: FaceBox) -> float:
    """Return where the bottom edge of the face box falls in the output frame, in pixels.

    The first row below the face: `face_box_px(...).y2 + 1`, that is (face y + face
    height - window y) x 1920 / window height. The captions call it the chin. Test
    stretch, frame 0: (225 + 549) x 1920 / 1080 = 1376. Over the whole stretch the chin
    goes from y = 1376 to 1680 (docs/03 §5.4, step 5).

    >>> window = CropKeyframe(t_ms=0, x=820, y=0, w=608, h=1080)
    >>> face_bottom_px(window, FaceBox(t_ms=0, x=849, y=225, w=549, h=549, score=0.97))
    1376.0
    """
    return face_box_px(keyframe, face).y2 + 1


def line_center_y(
    start_frame: int,
    end_frame: int,
    keyframes: list[CropKeyframe],
    faces: list[FaceBox],
    cut_frame_ms: list[int],
    style: CaptionStyle,
    safe_zone: SafeZone = ORGANIC_SAFE_ZONE,
) -> int:
    """Return the vertical center of a line's box: just below the lowest face of its frames.

    The top of the box goes `face_gap_px` below the lowest chin (`face_bottom_px`,
    rounded up) on the frames the line is shown, so the line never moves while it is
    on screen and never covers the face (docs/03 §5.4, step 5). The top is never lower
    than 1920 - box height, so the box stays inside the frame. `face_at` holds the last
    box across a gap, so the line only goes without a face when `faces` is empty; then
    the box sits on the bottom edge of `safe_zone`. The center is top + box height // 2.

    Args:
        start_frame: First frame of the line.
        end_frame: First frame after the line.
        keyframes: The camera path, one crop window per frame.
        faces: Boxes of the main face, in mezzanine pixels, sorted by `t_ms`.
        cut_frame_ms: Start of each cut frame, in clip milliseconds
            (`cut_frame_starts_ms`), so each frame uses the face of its own shot.
        style: The caption style: `face_gap_px` and `box_height_px`.
        safe_zone: Margins used when there is no face at all.

    Returns:
        The center row of the box, in output pixels.

    Example:
        Test stretch: the first line ("And if your brand", frames 2 to 44) has its
        lowest chin at 1568, so its top is 1568 + 20 = 1588 and its center
        1588 + 108 // 2 = 1642. Over the 27 lines the lowest chin goes from 1483 to
        1680, and the centers from 1483 + 74 = 1557 to 1680 + 74 = 1754 (docs/03 §5.4,
        step 5). Without faces the box ends at 1920 - 400 = 1520, so its top is
        1520 - 108 = 1412 and its center 1412 + 54 = 1466. On frame 0 of the test
        stretch alone, the chin at 1376 gives 1376 + 20 + 54 = 1450.

        >>> window = [CropKeyframe(t_ms=0, x=820, y=0, w=608, h=1080)]
        >>> face = FaceBox(t_ms=0, x=849, y=225, w=549, h=549, score=0.97)
        >>> line_center_y(0, 1, window, [face], [], CaptionStyle())
        1450
        >>> line_center_y(0, 1, window, [], [], CaptionStyle())
        1466
    """
    chins = [
        face_bottom_px(keyframe, face)
        for keyframe in keyframes[start_frame:end_frame]
        if (face := face_at(faces, keyframe.t_ms, cut_frame_ms)) is not None
    ]
    if chins:
        top = math.ceil(max(chins)) + style.face_gap_px
    else:
        top = OUTPUT_H - safe_zone.bottom - style.box_height_px
    top = min(top, OUTPUT_H - style.box_height_px)
    return top + style.box_height_px // 2


def merge_unshown(groups: list[list[ClipWord]], shown: list[bool]) -> list[list[ClipWord]]:
    """Join each line whose words never get a frame to its neighbour.

    A line with no shown word would never appear, so its words go at the start of the
    next line, or at the end of the previous one when it is the last (decided by Alex
    on 26 nov 2026, docs/03 §5.4, step 3). The joined line may then have more than
    `max_words_per_line` words or `max_chars_per_line` characters. Several lines in a
    row without frames all join the next line that has one.

    Args:
        groups: The lines, from `group_words`.
        shown: One flag per word, in the order of the groups: whether the word gets at
            least one frame of its own.

    Returns:
        The lines; each has at least one shown word. Empty if no word is shown.

    Example:
        "Yes." lasts 15 ms and ends its phrase, so it is a line of its own, and 990 ms
        and 1005 ms both fall on frame 30: it never gets a frame and joins "So we".

        >>> words = [
        ...     ClipWord(i=k, text=text, start_ms=0, end_ms=0, cut=0)
        ...     for k, text in enumerate(["Yes.", "So", "we"])
        ... ]
        >>> lines = merge_unshown([words[:1], words[1:]], [False, True, True])
        >>> [line_text(line) for line in lines]
        ['Yes. So we']
    """
    merged: list[list[ClipWord]] = []
    pending: list[ClipWord] = []
    position = 0
    for group in groups:
        flags = shown[position : position + len(group)]
        position += len(group)
        if any(flags):
            merged.append(pending + group)
            pending = []
        else:
            pending += group
    if pending and merged:
        merged[-1] = merged[-1] + pending
    return merged


def plan_captions(
    words: list[ClipWord],
    keyframes: list[CropKeyframe],
    faces: list[FaceBox],
    cut_frame_ms: list[int],
    style: CaptionStyle,
    pause_max_ms: int = 500,
    fps: int = 30,
) -> CaptionPlan:
    """Plan the captions of a clip: lines, the frames of each word and each line's height.

    Each word is said from the frame nearest its start, round(ms x 30 / 1000)
    (`ms_to_frame`), until the frame nearest the start of the next word; the last word
    until the end of the clip (one keyframe per frame). So the highlight is at most
    half a frame, 16.7 ms, away from the voice (docs/03 §5.4, step 3). A word whose
    next word starts on the same frame gets no frame and is listed in `skipped`, but
    stays in its line; a line left without frames joins its neighbour (`merge_unshown`).
    A line is shown from its first state to its last, back to back with the next one,
    and is placed by `line_center_y`.

    Args:
        words: The clip's words in play order, from `words_in_clip`.
        keyframes: The camera path, one crop window per frame of the clip.
        faces: Boxes of the main face, in mezzanine pixels, sorted by `t_ms`.
        cut_frame_ms: Start of each cut frame, in clip milliseconds
            (`cut_frame_starts_ms`).
        style: The caption style.
        pause_max_ms: Longest silence inside a phrase, in clip milliseconds. 500 by
            default, the Edit Spec's `pacing.pause_max_ms` (docs/03 §2.3).
        fps: Frame rate of the clip. 30 by default (docs/03 §5.6).

    Returns:
        The lines, their states and the skipped words.

    Example:
        Test stretch: 27 lines, 78 events and no skipped word. "And" starts at 60 ms,
        60 x 30 / 1000 = 1.8 -> frame 2, and "if" at 365 ms, 10.95 -> frame 11, so
        "And" is highlighted on frames 2 to 10. The first line is shown on frames 2
        to 44, until "isn't" starts a new line on frame 45.

        >>> words = [
        ...     ClipWord(i=29, text="And", start_ms=60, end_ms=124, cut=0),
        ...     ClipWord(i=30, text="if", start_ms=365, end_ms=462, cut=0),
        ... ]
        >>> still = [CropKeyframe(t_ms=round(f * 1000 / 30), x=820, y=0, w=608, h=1080)
        ...          for f in range(30)]
        >>> plan = plan_captions(words, still, [], [], CaptionStyle())
        >>> [(event.word, event.start_frame, event.end_frame) for event in plan.events]
        [(0, 2, 11), (1, 11, 30)]
    """
    grouped = group_words(words, style, pause_max_ms)
    flat = [word for group in grouped for word in group]
    total_frames = len(keyframes)
    starts = [ms_to_frame(word.start_ms, fps) for word in flat]
    ends = [*starts[1:], total_frames]
    shown = [end > start for start, end in zip(starts, ends, strict=True)]
    groups = merge_unshown(grouped, shown)
    span = {word.i: (start, end) for word, start, end in zip(flat, starts, ends, strict=True)}

    lines: list[CaptionLine] = []
    events: list[CaptionEvent] = []
    for group in groups:
        own = [
            CaptionEvent(
                line=len(lines),
                word=position,
                start_frame=span[word.i][0],
                end_frame=span[word.i][1],
            )
            for position, word in enumerate(group)
            if span[word.i][1] > span[word.i][0]
        ]
        start, end = own[0].start_frame, own[-1].end_frame
        lines.append(
            CaptionLine(
                words=group,
                start_frame=start,
                end_frame=end,
                center_y=line_center_y(start, end, keyframes, faces, cut_frame_ms, style),
            )
        )
        events.extend(own)
    skipped = [word.i for word, keep in zip(flat, shown, strict=True) if not keep]
    return CaptionPlan(lines=lines, events=events, skipped=skipped)


def ass_color(hex_color: str, alpha: int = 0) -> str:
    """Return a `#RRGGBB` color as ASS writes it in a style: `&HAABBGGRR`.

    ASS writes the alpha first and the channels in reverse order: blue, green, red,
    in upper-case hexadecimal.

    Args:
        hex_color: The color, `#RRGGBB`.
        alpha: Transparency, 0 to 255. 0, the default, is opaque.

    Returns:
        The style color, such as `&H002A7BFF` for the orange #FF7B2A.

    >>> ass_color("#FF7B2A")
    '&H002A7BFF'
    """
    red, green, blue = hex_color[1:3], hex_color[3:5], hex_color[5:7]
    return f"&H{alpha:02X}{blue}{green}{red}".upper()


def ass_override_color(hex_color: str) -> str:
    """Return a `#RRGGBB` color as an ASS override tag takes it: `&HBBGGRR&`.

    The same reversed channels as `ass_color`, without the alpha and closed by `&`.
    `event_text` uses it in the `1c` tag that colors the word being said.

    >>> ass_override_color("#FF7B2A"), ass_override_color("#ffffff")
    ('&H2A7BFF&', '&HFFFFFF&')
    """
    return f"&H{ass_color(hex_color)[4:]}&"


def hex_color(ass: str) -> str:
    """Return an ASS color (`&HAABBGGRR` or `&HBBGGRR&`) as `#RRGGBB`, like `ass_color` reversed.

    The alpha, if any, is dropped. `read_ass_style` uses it to read the colors back.

    >>> hex_color("&H002A7BFF"), hex_color("&H2A7BFF&")
    ('#FF7B2A', '#FF7B2A')
    """
    digits = ass.strip("&Hh").rjust(8, "0")[-6:]
    return f"#{digits[4:6]}{digits[2:4]}{digits[0:2]}".upper()


def ass_time(frame: int, fps: int = 30) -> str:
    """Return the ASS time that makes an event start on a frame: half a frame before it.

    The same time `sendcmd` uses (`command_time_s`), (n - 0.5) / 30 s, written in
    centiseconds (`H:MM:SS.cc`) because ASS has no finer unit. libass shows an event on
    every frame whose time is at or after its start. Rounding to centiseconds moves the
    time by 5 ms at most, and half a frame is 16.7 ms, so the time stays after the start
    of frame n - 1 and before that of frame n (docs/03 §5.4, step 3). Frame 0 gets 0.

    Args:
        frame: Index of the frame, 0 or more.
        fps: Frame rate of the clip. 30 by default (docs/03 §5.6).

    Returns:
        The time, such as `0:00:00.35`.

    Example:
        Test stretch: "if" is highlighted from frame 11, which starts at 366.7 ms;
        (11 - 0.5) / 30 = 0.35 s. The last line ends after frame 1003:
        (1004 - 0.5) / 30 = 33.45 s.

        >>> ass_time(11), ass_time(1004)
        ('0:00:00.35', '0:00:33.45')
    """
    centiseconds = round(command_time_s(frame, fps) * 100)
    hours, rest = divmod(centiseconds, 360_000)
    minutes, rest = divmod(rest, 6_000)
    seconds, cents = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{cents:02d}"


def pop_tags(elapsed_ms: int, style: CaptionStyle) -> str:
    """Return the scale tags of a line `elapsed_ms` after it appears: the "pop" entrance.

    The line grows in a straight line from `pop_from` to full size over `pop_ms`:
    scale = 100 x (pop_from + (1 - pop_from) x elapsed / pop_ms) %, with `fscx` and
    `fscy` tags, then a `t` tag animates it to 100 % in the time left. An event that
    starts in the middle of the pop starts at the scale reached by then, so the
    entrance does not restart when the highlight moves (docs/03 §5.4, step 4).

    Args:
        elapsed_ms: Time since the line appeared, in milliseconds, 0 or more.
        style: The caption style: `pop_from` and `pop_ms`.

    Returns:
        The override tags, or an empty string once the pop is over.

    Example:
        33 ms in: 100 x (0.80 + 0.20 x 33 / 80) = 88.25 %, written 88.2, with
        80 - 33 = 47 ms left. Each event starts half a frame early (`ass_time`), so
        at 30 fps a new line is drawn 16.7, 50 and 83.3 ms into the pop:
        80 + 20 x 16.7 / 80 = 84 %, 92.5 % and 100 %. On the test stretch the first
        line measures 430, 476 and 518 px wide on those frames (docs/03 §5.4).

        >>> "fscx88.2" in pop_tags(33, CaptionStyle())
        True
        >>> pop_tags(80, CaptionStyle())
        ''
    """
    if elapsed_ms >= style.pop_ms:
        return ""
    scale = 100 * (style.pop_from + (1 - style.pop_from) * elapsed_ms / style.pop_ms)
    return (
        f"\\fscx{scale:.1f}\\fscy{scale:.1f}\\t(0,{style.pop_ms - elapsed_ms},\\fscx100\\fscy100)"
    )


def ass_header(style: CaptionStyle) -> str:
    """Return the `[Script Info]` and `[V4+ Styles]` sections and the `[Events]` heading.

    `PlayResX` and `PlayResY` are 1080x1920, so every ASS position is an output pixel.
    `WrapStyle: 2` turns off libass's own line wrapping: the lines are already grouped.
    `YCbCr Matrix: TV.709` makes the `ass` filter convert the colors for a BT.709 clip;
    without it FFmpeg 9.0.2 used BT.601 and the orange came out #FF8124 (255, 129, 36,
    measured without compression), with it (254, 122, 41) (docs/03 §5.4, step 7).

    The style line carries the font, size and bold, the text color as primary, the
    highlight color as secondary and the box color as outline and back color, so
    `read_ass_style` can rebuild the style from it. `BorderStyle` 3 draws an opaque box
    behind the text, with `Outline` = `box_padding_px` (18 px) as its margin, and
    `Alignment` 5 centers the text on the point each event gives with `pos`.

    Args:
        style: The caption style.

    Returns:
        The header text, without a final newline.

    Example:
        >>> ass_header(CaptionStyle()).splitlines()[10].split(",")[:6]
        ['Style: Caption', 'Figtree', '72', '&H002A7BFF', '&H00FFFFFF', '&H00000000']
    """
    bold = -1 if style.bold else 0
    padding = style.box_padding_px
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {OUTPUT_W}",
            f"PlayResY: {OUTPUT_H}",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: TV.709",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: {STYLE_NAME},{style.font_name},{style.size_px},"
            f"{ass_color(style.text_color)},{ass_color(style.highlight_color)},"
            f"{ass_color(style.box_color)},{ass_color(style.box_color)},"
            f"{bold},0,0,0,100,100,0,0,3,{padding},0,5,0,0,0,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )


def read_ass_style(ass_text: str) -> CaptionStyle:
    """Rebuild the caption style from the `Style:` line `ass_header` wrote.

    Font, size, bold, text, highlight and box colors and the box padding come from the
    file; the rest keeps the `CaptionStyle` defaults. `compose` and `verify-clip` check
    the captions against this style, the one in the file, not against defaults
    (docs/03 §5.4, row "Fuentes", and §5.7).

    Args:
        ass_text: The whole text of a captions file.

    Returns:
        The style the file was written with.

    Raises:
        ValueError: If the file has no `Style: Caption,...` line.

    Example:
        >>> style = read_ass_style(ass_header(CaptionStyle(size_px=64)))
        >>> style.font_name, style.size_px, style.text_color, style.bold
        ('Figtree', 64, '#FF7B2A', True)
    """
    for row in ass_text.splitlines():
        if row.startswith(f"Style: {STYLE_NAME},"):
            fields = row.removeprefix("Style: ").split(",")
            return CaptionStyle(
                font_name=fields[1],
                size_px=int(fields[2]),
                text_color=hex_color(fields[3]),
                highlight_color=hex_color(fields[4]),
                box_color=hex_color(fields[5]),
                bold=fields[7] == "-1",
                box_padding_px=int(fields[16]),
            )
    raise ValueError(f"no 'Style: {STYLE_NAME},' line in the captions file")


def event_text(
    line: CaptionLine, event: CaptionEvent, style: CaptionStyle, keywords: frozenset[int]
) -> str:
    """Return the text of one state of a line, with the word being said highlighted.

    The words are joined by spaces. The word being said is wrapped in two `1c` override
    tags: one with `highlight_color` before it and one back to `text_color` after it.
    With `highlight_mode` `keywords` it is only wrapped when its transcript index is in
    `keywords`; with `none`, never.

    Args:
        line: The line the event belongs to.
        event: The state: `event.word` is the position of the word being said.
        style: The caption style: colors and `highlight_mode`.
        keywords: Transcript indices of the keywords, used with `keywords` mode.

    Returns:
        The `Text` field of the `Dialogue` row, without the position and pop tags.

    Example:
        Test stretch, second state of the first line: "And", then "if" in white, then
        "your brand" in orange.
    """
    highlight = ass_override_color(style.highlight_color)
    normal = ass_override_color(style.text_color)
    parts: list[str] = []
    for position, word in enumerate(line.words):
        text = caption_text(word.text)
        highlighted = position == event.word and (
            style.highlight_mode == "word"
            or (style.highlight_mode == "keywords" and word.i in keywords)
        )
        parts.append(f"{{\\1c{highlight}}}{text}{{\\1c{normal}}}" if highlighted else text)
    return " ".join(parts)


def captions_ass(
    plan: CaptionPlan,
    style: CaptionStyle,
    keywords: frozenset[int] = frozenset(),
    fps: int = 30,
) -> str:
    """Write the captions of a plan as the text of an ASS file.

    The header comes from `ass_header`, then one `Dialogue` per event, from
    `ass_time(start_frame)` to `ass_time(end_frame)`. Each event places its line with
    `an5` and `pos` at x = 540 and the line's `center_y`, adds the pop tags
    (`pop_tags`) for the time since the line appeared, (event frame - line frame) x
    1000 / 30 -> ms, and the text of `event_text`. Its Name field is
    `<line>:<transcript index>` of the word being said, so `verify-clip` can read back
    which word each event is about (`read_ass_events`).

    Args:
        plan: The lines and events, from `plan_captions`.
        style: The caption style the plan was made with.
        keywords: Transcript indices to highlight when `highlight_mode` is `keywords`.
            Empty by default.
        fps: Frame rate of the clip. 30 by default (docs/03 §5.6).

    Returns:
        The file text, ending with a newline.

    Example:
        Test stretch: 78 `Dialogue` rows. The first one runs from 0:00:00.05 to
        0:00:00.35 (frames 2 to 10), is named `0:29` ("And", word 29) and is placed
        at (540, 1642) with the pop from 80 %. The second, `0:30` ("if"), starts
        (11 - 2) x 1000 / 30 = 300 ms after the line appeared, past the 80 ms pop, so
        it has no scale tags.
    """
    rows = [ass_header(style)]
    for event in plan.events:
        line = plan.lines[event.line]
        elapsed_ms = round((event.start_frame - line.start_frame) * 1000 / fps)
        tags = f"\\an5\\pos({OUTPUT_W // 2},{line.center_y}){pop_tags(elapsed_ms, style)}"
        name = f"{event.line}:{line.words[event.word].i}"
        rows.append(
            f"Dialogue: 0,{ass_time(event.start_frame, fps)},{ass_time(event.end_frame, fps)},"
            f"{STYLE_NAME},{name},0,0,0,,{{{tags}}}{event_text(line, event, style, keywords)}"
        )
    return "\n".join(rows) + "\n"
