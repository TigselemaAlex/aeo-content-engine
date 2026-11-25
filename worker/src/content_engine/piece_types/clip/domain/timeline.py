"""Turn a word range of the transcript into the cuts of a clip (docs/03 §5.1).

Pure code: no disk, network or FFmpeg. Words are addressed by their position in the
transcript word list. Every `Cut` is in milliseconds of the original video's clock;
"clip time" is milliseconds from the start of the clip, which is also the start of the
mezzanine (docs/03 §5.2). Frame counts assume the mezzanine's constant 30 fps.
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from content_engine.shared.transcript import Word


class Segment(BaseModel):
    """A range of consecutive transcript words, both ends included.

    It is the unit the edit decisions use (`segments` in docs/03 §4.2) and what the
    timeline splits around fillers and long pauses. Immutable.

    Attributes:
        from_word: Position of the first word in the transcript word list. 0 or more.
        to_word: Position of the last word, included. 0 or more and not lower than
            `from_word`, so a one-word segment has both equal.
    """

    from_word: int = Field(ge=0)
    to_word: int = Field(ge=0)

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def check_order(self) -> Self:
        """Reject a segment that ends before it starts.

        Returns:
            The segment itself, unchanged.

        Raises:
            ValueError: If `to_word` is lower than `from_word`. Pydantic reports it
                as a `ValidationError`.
        """
        if self.to_word < self.from_word:
            raise ValueError("to_word must not be lower than from_word")
        return self


class Cut(BaseModel):
    """A time range of the original video that goes into the clip.

    The same type holds the audio ranges (`Timeline.cuts`) and the image ranges
    (`Timeline.video_cuts`). Immutable.

    Attributes:
        start_ms: Where the range starts, in milliseconds of the original video. 0 or more.
        end_ms: Where the range ends, in milliseconds of the original video. Strictly
            after `start_ms`, so a cut always lasts at least 1 ms.
    """

    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def check_order(self) -> Self:
        """Reject a cut that does not end after it starts.

        Returns:
            The cut itself, unchanged.

        Raises:
            ValueError: If `end_ms` is equal to or lower than `start_ms`. Pydantic
                reports it as a `ValidationError`.
        """
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be after start_ms")
        return self


class Timeline(BaseModel):
    """The cuts of one clip, in the order they play, for audio and image separately.

    Audio and image differ only by the J cuts (docs/03 §5.1, step 5): at each join the
    audio of the next cut starts before its image. Both lists play back to back, have
    one entry per cut and add up to the same duration, so the clip never drifts out of
    sync. The audio cuts are the reference for clip time, because subtitles follow the
    audio. Immutable.

    Attributes:
        cuts: Audio ranges of the original video, in play order (a hook may come
            before earlier words).
        video_cuts: Image ranges of the original video, one per audio cut, as built by
            `add_j_cuts`. They must last the same total as `cuts`.

    Example:
        Two cuts with a 133 ms J cut (4 frames at 30 fps): the first image runs 133 ms
        longer than its audio and the second starts 133 ms later.

        >>> audio = [Cut(start_ms=0, end_ms=1620), Cut(start_ms=2940, end_ms=5620)]
        >>> timeline = Timeline(cuts=audio, video_cuts=add_j_cuts(audio, j_cut_ms=133))
        >>> timeline.video_cuts
        [Cut(start_ms=0, end_ms=1753), Cut(start_ms=3073, end_ms=5620)]
    """

    cuts: list[Cut]
    video_cuts: list[Cut]

    model_config = ConfigDict(frozen=True)

    @property
    def duration_ms(self) -> int:
        """How long the clip lasts, in milliseconds.

        It is the sum of the audio cut durations; the image cuts add up to the same.

        Example:
            1000 ms + 500 ms = 1500 ms.

            >>> cuts = [Cut(start_ms=0, end_ms=1000), Cut(start_ms=3000, end_ms=3500)]
            >>> Timeline(cuts=cuts, video_cuts=cuts).duration_ms
            1500
        """
        return sum(cut.end_ms - cut.start_ms for cut in self.cuts)

    @model_validator(mode="after")
    def check_video_cuts(self) -> Self:
        """Reject image cuts that would put audio and image out of sync.

        Returns:
            The timeline itself, unchanged.

        Raises:
            ValueError: If `video_cuts` does not have one entry per audio cut, or if
                they do not last the same total as `cuts`. Pydantic reports it as a
                `ValidationError`.
        """
        if len(self.cuts) != len(self.video_cuts):
            raise ValueError("video_cuts must have one cut per audio cut")
        video_cut_duration_ms = sum(
            video_cut.end_ms - video_cut.start_ms for video_cut in self.video_cuts
        )
        if video_cut_duration_ms != self.duration_ms:
            raise ValueError("video_cuts must last the same as the audio cuts")
        return self

    @property
    def video_cut_points_ms(self) -> list[int]:
        """Clip times where the image jumps from one cut to the next.

        Each point is the running total of the image cut durations, so it falls a J
        cut later than the audio join. The camera path places its cut bridges here
        (docs/03 §5.3, step 6). There is one point fewer than cuts: none at the start
        and none at the end.

        Returns:
            Milliseconds from the start of the clip, in increasing order. Empty for a
            single cut.

        Example:
            The first image cut lasts 1620 + 133 = 1753 ms, so the image jumps at 1753 ms
            while the audio joins at 1620 ms.

            >>> audio = [Cut(start_ms=0, end_ms=1620), Cut(start_ms=2940, end_ms=5620)]
            >>> timeline = Timeline(cuts=audio, video_cuts=add_j_cuts(audio, j_cut_ms=133))
            >>> timeline.video_cut_points_ms
            [1753]
        """
        points: list[int] = []
        elapsed_ms = 0
        for video_cut in self.video_cuts[:-1]:
            elapsed_ms += video_cut.end_ms - video_cut.start_ms
            points.append(elapsed_ms)
        return points

    def to_clip_ms(self, original_ms: int) -> int | None:
        """Return where a time of the original video lands in the clip.

        This is the time map of docs/03 §5.1, built on the audio cuts. It walks the
        cuts in play order and, for the first one that contains `original_ms` (both
        ends included), adds the offset inside that cut to the time the cut starts in
        the clip.

        Args:
            original_ms: A time in milliseconds of the original video.

        Returns:
            Milliseconds from the start of the clip, or `None` if that moment was cut
            out (a filler, a long pause or anything outside the cuts).

        Example:
            With cuts 0-1000 and 2000-3500 ms, the second cut starts at 1000 ms in the
            clip, so 2500 ms lands at 1000 + (2500 - 2000) = 1500 ms. 1500 ms was in the
            removed pause.

            >>> cuts = [Cut(start_ms=0, end_ms=1000), Cut(start_ms=2000, end_ms=3500)]
            >>> timeline = Timeline(cuts=cuts, video_cuts=cuts)
            >>> timeline.to_clip_ms(2500)
            1500
            >>> timeline.to_clip_ms(1500) is None
            True
        """
        cut_start_in_clip_ms = 0
        for cut in self.cuts:
            if cut.start_ms <= original_ms <= cut.end_ms:
                return cut_start_in_clip_ms + (original_ms - cut.start_ms)
            cut_start_in_clip_ms += cut.end_ms - cut.start_ms
        return None


def _check_segment_in_transcript(segment: Segment, words: list[Word]) -> None:
    """Raise `ValueError` if the segment ends past the last word of the transcript."""
    if segment.to_word >= len(words):
        raise ValueError(
            f"segment ends at word index {segment.to_word} "
            f"but the transcript only has indices 0 to {len(words) - 1}"
        )


def segment_to_cut(segment: Segment, words: list[Word]) -> Cut:
    """Return the exact time range a segment covers, with no margin.

    The cut starts where the first word starts and ends where the last word ends.
    `segment_to_padded_cut` adds the margins that keep syllables whole.

    Args:
        segment: The word range.
        words: The transcript words, indexed by position.

    Returns:
        A cut in milliseconds of the original video.

    Raises:
        ValueError: If the segment ends past the last word of `words`.

    Example:
        Words that start every 1000 ms and last 500 ms: word 1 starts at 1000 ms and
        word 3 ends at 3000 + 500 = 3500 ms.

        >>> words = [
        ...     Word(i=k, text=f"word{k}", start_ms=k * 1000, end_ms=k * 1000 + 500,
        ...          speaker="A", confidence=1.0, is_disfluency=False)
        ...     for k in range(6)
        ... ]
        >>> segment_to_cut(Segment(from_word=1, to_word=3), words)
        Cut(start_ms=1000, end_ms=3500)
    """
    _check_segment_in_transcript(segment=segment, words=words)

    first = words[segment.from_word]
    last = words[segment.to_word]
    return Cut(start_ms=first.start_ms, end_ms=last.end_ms)


def split_out_fillers(segment: Segment, words: list[Word]) -> list[Segment]:
    """Split a segment into the runs of words that are not fillers.

    Fillers are the words marked `is_disfluency` ("um", "uh"; docs/03 §3). Each run of
    one or more fillers is dropped and the words around it become separate segments
    (docs/03 §5.1, step 2). Fillers at the edges are dropped too.

    Args:
        segment: The word range to clean.
        words: The transcript words, indexed by position.

    Returns:
        The remaining segments in order. Empty if every word is a filler.

    Raises:
        ValueError: If the segment ends past the last word of `words`.

    Example:
        Word 2 is a filler, so words 0 to 5 become 0-1 and 3-5.

        >>> words = [
        ...     Word(i=k, text=f"word{k}", start_ms=k * 1000, end_ms=k * 1000 + 500,
        ...          speaker="A", confidence=1.0, is_disfluency=k == 2)
        ...     for k in range(6)
        ... ]
        >>> split_out_fillers(Segment(from_word=0, to_word=5), words)
        [Segment(from_word=0, to_word=1), Segment(from_word=3, to_word=5)]
    """
    _check_segment_in_transcript(segment=segment, words=words)

    pieces: list[Segment] = []
    start: int | None = None

    for k in range(segment.from_word, segment.to_word + 1):
        if words[k].is_disfluency:
            if start is not None:
                pieces.append(Segment(from_word=start, to_word=k - 1))
                start = None
        elif start is None:
            start = k

    if start is not None:
        pieces.append(Segment(from_word=start, to_word=segment.to_word))

    return pieces


def split_at_long_pauses(
    segment: Segment, words: list[Word], pause_max_ms: int, keep_pauses_after: tuple[int, ...] = ()
) -> list[Segment]:
    """Split a segment at every silence longer than `pause_max_ms`.

    The silence between two words is the next word's start minus this word's end.
    When it is longer than `pause_max_ms` the segment is split there, the same way a
    filler splits it (docs/03 §5.1, step 3). There is no separate pause length: the
    silence left in the clip is the cut margins, about 120 + 60 = 180 ms (decision
    "Pausas largas en el timeline", docs/00).

    Args:
        segment: The word range to split.
        words: The transcript words, indexed by position.
        pause_max_ms: Longest silence kept, in milliseconds. A silence of exactly this
            length is kept. Edit Spec `pacing.pause_max_ms`, 500 by default
            (docs/03 §2.3).
        keep_pauses_after: Positions of words whose following silence is kept at any
            length: the emphasis pauses (`keep_pauses.after_word`, docs/03 §4.2).

    Returns:
        The pieces in order. A single piece equal to `segment` if no silence is too long.

    Raises:
        ValueError: If the segment ends past the last word of `words`.

    Example:
        Words that start every 1000 ms and last 500 ms leave 1000 - 500 = 500 ms of
        silence. With 500 ms nothing splits, because 500 is not longer than 500. With
        400 ms every silence splits, except the one after word 3, kept as emphasis.

        >>> words = [
        ...     Word(i=k, text=f"word{k}", start_ms=k * 1000, end_ms=k * 1000 + 500,
        ...          speaker="A", confidence=1.0, is_disfluency=False)
        ...     for k in range(6)
        ... ]
        >>> split_at_long_pauses(Segment(from_word=3, to_word=5), words, pause_max_ms=500)
        [Segment(from_word=3, to_word=5)]
        >>> split_at_long_pauses(
        ...     Segment(from_word=3, to_word=5), words, pause_max_ms=400, keep_pauses_after=(3,)
        ... )
        [Segment(from_word=3, to_word=4), Segment(from_word=5, to_word=5)]
    """
    _check_segment_in_transcript(segment=segment, words=words)

    pieces: list[Segment] = []
    start: int = segment.from_word

    for k in range(segment.from_word, segment.to_word):
        gap_ms = words[k + 1].start_ms - words[k].end_ms

        if gap_ms > pause_max_ms and k not in keep_pauses_after:
            pieces.append(Segment(from_word=start, to_word=k))
            start = k + 1

    pieces.append(Segment(from_word=start, to_word=segment.to_word))
    return pieces


def segment_to_padded_cut(
    segment: Segment, words: list[Word], pad_before_ms: int = 60, pad_after_ms: int = 120
) -> Cut:
    """Return the time range of a segment with a margin on each side.

    The margins keep the first and last syllables whole: the cut never ends inside a
    word (docs/03 §5.1, step 4). The start moves `pad_before_ms` earlier but never
    before 0 nor before the previous word ends. The end moves `pad_after_ms` later but
    never past the start of the next word. After the last word of the transcript the
    end is not limited.

    Args:
        segment: The word range.
        words: The transcript words, indexed by position.
        pad_before_ms: Margin before the first word, in milliseconds. 60 by default
            (docs/03 §5.1); kept after listening to a 51 s stretch (words 185 to 298)
            of the first test recording, replaced in T2.1 (decision "Extracción del
            intermedio", docs/00).
        pad_after_ms: Margin after the last word, in milliseconds. 120 by default, from
            the same source and test.

    Returns:
        A cut in milliseconds of the original video.

    Raises:
        ValueError: If the segment ends past the last word of `words`.

    Example:
        Words start every 1000 ms and last 500 ms. Words 0-1: start max(0 - 60, 0) = 0
        and end min(1500 + 120, 2000) = 1620. Words 3-5: start max(3000 - 60, 2500) =
        2940 and end 5500 + 120 = 5620, since word 5 is the last one.

        >>> words = [
        ...     Word(i=k, text=f"word{k}", start_ms=k * 1000, end_ms=k * 1000 + 500,
        ...          speaker="A", confidence=1.0, is_disfluency=False)
        ...     for k in range(6)
        ... ]
        >>> segment_to_padded_cut(Segment(from_word=0, to_word=1), words)
        Cut(start_ms=0, end_ms=1620)
        >>> segment_to_padded_cut(Segment(from_word=3, to_word=5), words)
        Cut(start_ms=2940, end_ms=5620)
    """
    cut = segment_to_cut(segment=segment, words=words)

    start_ms = max(cut.start_ms - pad_before_ms, 0)
    if segment.from_word > 0:
        previous_word = words[segment.from_word - 1]
        start_ms = max(start_ms, previous_word.end_ms)

    end_ms = cut.end_ms + pad_after_ms

    if segment.to_word < len(words) - 1:
        next_word = words[segment.to_word + 1]
        end_ms = min(end_ms, next_word.start_ms)

    return Cut(start_ms=start_ms, end_ms=end_ms)


def frames_to_ms(frames: int, fps: int = 30) -> int:
    """Return how many milliseconds a number of frames lasts.

    The count is frames x 1000 / fps -> ms, rounded to the nearest millisecond.

    Args:
        frames: Number of frames. 0 or more.
        fps: Frames per second. Positive; 30 by default, the mezzanine's frame rate
            (docs/03 §5.2).

    Returns:
        The duration in milliseconds.

    Raises:
        ValueError: If `frames` is negative or `fps` is 0 or less.

    Example:
        4 x 1000 / 30 = 133.3 -> 133 ms, and 5 x 1000 / 30 = 166.7 -> 167 ms.

        >>> frames_to_ms(4)
        133
        >>> frames_to_ms(5)
        167
    """
    if frames < 0:
        raise ValueError("frames must not be negative")
    if fps <= 0:
        raise ValueError("fps must be positive")

    return round(frames * 1000 / fps)


def add_j_cuts(cuts: list[Cut], j_cut_ms: int) -> list[Cut]:
    """Build the image cuts so that, at each join, the next audio starts first.

    The audio cuts stay as they are. At every join the image of the earlier cut runs
    `j_cut_ms` longer and the image of the later cut starts `j_cut_ms` later
    (docs/03 §5.1, step 5). So the first image lasts `j_cut_ms` more than its audio,
    the last one `j_cut_ms` less and the middle ones the same: in total the image
    lasts as long as the audio. A single cut is returned unchanged.

    Args:
        cuts: Audio cuts in play order, in milliseconds of the original video.
        j_cut_ms: How long the next audio plays over the earlier image, in
            milliseconds. 0 or more; `build_timeline` passes 133 (4 frames at 30 fps).

    Returns:
        One image cut per audio cut, in the same order.

    Raises:
        ValueError: If `j_cut_ms` is negative, or if a cut would end up with no image,
            which happens when the last cut lasts `j_cut_ms` or less.

    Example:
        With 133 ms: the first image ends at 1620 + 133 = 1753 ms and the second
        starts at 2940 + 133 = 3073 ms. 1753 + 2547 = 4300 ms, the same as the audio
        1620 + 2680.

        >>> add_j_cuts([Cut(start_ms=0, end_ms=1620), Cut(start_ms=2940, end_ms=5620)], 133)
        [Cut(start_ms=0, end_ms=1753), Cut(start_ms=3073, end_ms=5620)]
    """
    if j_cut_ms < 0:
        raise ValueError("j_cut_ms must not be negative")

    last_index = len(cuts) - 1
    video_cuts: list[Cut] = []

    for k, cut in enumerate(cuts):
        start_ms = cut.start_ms + (j_cut_ms if k > 0 else 0)
        end_ms = cut.end_ms + (j_cut_ms if k < last_index else 0)

        if end_ms <= start_ms:
            raise ValueError(
                f"cut {k} lasts {cut.end_ms - cut.start_ms} ms too short for {j_cut_ms} ms J cut"
            )
        video_cuts.append(Cut(start_ms=start_ms, end_ms=end_ms))

    return video_cuts


def build_timeline(
    words: list[Word],
    segment: Segment,
    pause_max_ms: int = 500,
    j_cut_frames: tuple[int, int] = (3, 5),
    keep_pauses_after: tuple[int, ...] = (),
    fps: int = 30,
) -> Timeline:
    """Build the timeline of a clip from one word range of the transcript.

    It follows docs/03 §5.1: drop the fillers (`split_out_fillers`), split each
    remaining piece at the long pauses (`split_at_long_pauses`), add the margins to
    each piece (`segment_to_padded_cut`) and build the image cuts with a J cut at every
    join (`add_j_cuts`). Fillers are always removed. The J cut is always the middle of
    `j_cut_frames`, (min + max) // 2 frames, so running it again gives the same result
    (decision "J cuts en el timeline", docs/00).

    Args:
        words: The transcript words, indexed by position.
        segment: The word range the clip is made of.
        pause_max_ms: Longest silence kept, in milliseconds. Edit Spec
            `pacing.pause_max_ms`, 500 by default (docs/03 §2.3).
        j_cut_frames: `(min, max)` frames the next audio starts before its image. Edit
            Spec `pacing.j_cut_frames`, (3, 5) by default (docs/03 §2.3).
        keep_pauses_after: Positions of words whose following silence is kept at any
            length (`keep_pauses.after_word`, docs/03 §4.2).
        fps: Frame rate used to turn `j_cut_frames` into milliseconds. 30 by default,
            the mezzanine's frame rate (docs/03 §5.2).

    Returns:
        The audio cuts and the image cuts of the clip.

    Raises:
        ValueError: If the segment ends past the last word of `words`, if every word in
            it is a filler, or if the last cut lasts no longer than the J cut.

    Example:
        Words start every 1000 ms, last 500 ms and word 2 is a filler. The fillers
        leave words 0-1 and 3-5; with margins the cuts are 0-1620 and 2940-5620 ms.
        The J cut is (3 + 5) // 2 = 4 frames, 4 x 1000 / 30 = 133 ms, so the image cuts
        are 0-1753 and 3073-5620 ms. The clip lasts 1620 + 2680 = 4300 ms.

        >>> words = [
        ...     Word(i=k, text=f"word{k}", start_ms=k * 1000, end_ms=k * 1000 + 500,
        ...          speaker="A", confidence=1.0, is_disfluency=k == 2)
        ...     for k in range(6)
        ... ]
        >>> timeline = build_timeline(words, Segment(from_word=0, to_word=5))
        >>> timeline.cuts
        [Cut(start_ms=0, end_ms=1620), Cut(start_ms=2940, end_ms=5620)]
        >>> timeline.video_cuts
        [Cut(start_ms=0, end_ms=1753), Cut(start_ms=3073, end_ms=5620)]
        >>> timeline.duration_ms
        4300
    """
    without_fillers = split_out_fillers(segment=segment, words=words)
    if not without_fillers:
        raise ValueError(
            f"words {segment.from_word} to {segment.to_word} are all fillers, nothing left to cut"
        )

    segments: list[Segment] = []

    for part in without_fillers:
        segments.extend(
            split_at_long_pauses(
                segment=part,
                words=words,
                pause_max_ms=pause_max_ms,
                keep_pauses_after=keep_pauses_after,
            )
        )

    cuts = [segment_to_padded_cut(segment=piece, words=words) for piece in segments]

    min_frames, max_frames = j_cut_frames
    j_cut_ms = frames_to_ms(frames=(min_frames + max_frames) // 2, fps=fps)
    video_cuts = add_j_cuts(cuts=cuts, j_cut_ms=j_cut_ms)

    return Timeline(cuts=cuts, video_cuts=video_cuts)


def words_to_clip_ms(word_indices: list[int], words: list[Word], timeline: Timeline) -> list[int]:
    """Return the clip time where each word starts.

    Claude marks moments with word positions, never milliseconds (docs/03 §4). This
    turns them into clip time with `Timeline.to_clip_ms` on each word's start, so the
    camera path can place its zooms (docs/03 §5.3, step 5).

    Args:
        word_indices: Positions of the words in the transcript word list.
        words: The transcript words, indexed by position.
        timeline: The clip's timeline, built from the same `words`.

    Returns:
        Milliseconds from the start of the clip, one per index and in the same order.

    Raises:
        ValueError: If an index is outside `words`, or if its word's start is not in
            any cut (for example, a filler that was removed).

    Example:
        With cuts 0-1620 and 2940-5620 ms, word 3 starts at 3000 ms: 60 ms into the
        second cut, which starts at 1620 ms in the clip, so 1620 + 60 = 1680 ms.

        >>> words = [
        ...     Word(i=k, text=f"word{k}", start_ms=k * 1000, end_ms=k * 1000 + 500,
        ...          speaker="A", confidence=1.0, is_disfluency=k == 2)
        ...     for k in range(6)
        ... ]
        >>> timeline = build_timeline(words, Segment(from_word=0, to_word=5))
        >>> words_to_clip_ms([0, 3], words, timeline)
        [0, 1680]
    """
    clip_ms: list[int] = []
    for index in word_indices:
        if not 0 <= index < len(words):
            raise ValueError(f"word {index} is not in the transcript")
        ms = timeline.to_clip_ms(words[index].start_ms)
        if ms is None:
            raise ValueError(f"word {index} ({words[index].text!r}) is not in the clip")
        clip_ms.append(ms)
    return clip_ms
