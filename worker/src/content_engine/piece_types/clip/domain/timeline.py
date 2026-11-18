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

    model_config = ConfigDict(frozen=True)

    @property
    def duration_ms(self) -> int:
        return sum(cut.end_ms - cut.start_ms for cut in self.cuts)


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


def split_out_filters(segment: Segment, words: list[Word]) -> list[Segment]:
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
