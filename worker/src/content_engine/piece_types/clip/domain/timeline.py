from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from content_engine.shared.transcript import Word


class Segment(BaseModel):
    from_word: int = Field(ge=0)
    to_word: int = Field(ge=0)

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def check_order(self) -> Self:
        if self.to_word < self.from_word:
            raise ValueError("to_word must not be lower than from_word")
        return self


class Cut(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def check_order(self) -> Self:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be after start_ms")
        return self


class Timeline(BaseModel):
    cuts: list[Cut]
    video_cuts: list[Cut]

    model_config = ConfigDict(frozen=True)

    @property
    def duration_ms(self) -> int:
        return sum(cut.end_ms - cut.start_ms for cut in self.cuts)

    @model_validator(mode="after")
    def check_video_cuts(self) -> Self:
        if len(self.cuts) != len(self.video_cuts):
            raise ValueError("video_cuts must be have one per audio cut")
        video_cut_duration_ms = sum(
            video_cut.end_ms - video_cut.start_ms for video_cut in self.video_cuts
        )
        if video_cut_duration_ms != self.duration_ms:
            raise ValueError("video_vuts must last the same as the audio cuts")
        return self

    @property
    def video_cut_points_ms(self) -> list[int]:
        """Clip times where the image jumps from one cut to the next."""
        points: list[int] = []
        elapsed_ms = 0
        for video_cut in self.video_cuts[:-1]:
            elapsed_ms += video_cut.end_ms - video_cut.start_ms
            points.append(elapsed_ms)
        return points

    def to_clip_ms(self, original_ms: int) -> int | None:
        cut_start_in_clip_ms = 0
        for cut in self.cuts:
            if cut.start_ms <= original_ms <= cut.end_ms:
                return cut_start_in_clip_ms + (original_ms - cut.start_ms)
            cut_start_in_clip_ms += cut.end_ms - cut.start_ms
        return None


def _check_segment_in_transcript(segment: Segment, words: list[Word]) -> None:
    if segment.to_word >= len(words):
        raise ValueError(
            f"segment ends at word index {segment.to_word} "
            f"but the transcript only has indices 0 to {len(words) - 1}"
        )


def segment_to_cut(segment: Segment, words: list[Word]) -> Cut:
    _check_segment_in_transcript(segment=segment, words=words)

    first = words[segment.from_word]
    last = words[segment.to_word]
    return Cut(start_ms=first.start_ms, end_ms=last.end_ms)


def split_out_fillers(segment: Segment, words: list[Word]) -> list[Segment]:
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
    if frames < 0:
        raise ValueError("frames mut not be negative")
    if fps <= 0:
        raise ValueError("fps mut be positive")

    return round(frames * 1000 / fps)


def add_j_cuts(cuts: list[Cut], j_cut_ms: int) -> list[Cut]:
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
    """Clip time where each word starts. Fails if a word was cut out of the clip."""
    clip_ms: list[int] = []
    for index in word_indices:
        if not 0 <= index < len(words):
            raise ValueError(f"word {index} is not in the transcript")
        ms = timeline.to_clip_ms(words[index].start_ms)
        if ms is None:
            raise ValueError(f"word {index} ({words[index].text!r}) is not in the clip")
        clip_ms.append(ms)
    return clip_ms
