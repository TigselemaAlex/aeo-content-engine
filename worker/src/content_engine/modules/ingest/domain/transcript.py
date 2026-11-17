from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

FILLER_WORDS = frozenset({"um", "umm", "uh", "uhm", "hmm", "er", "erm"})


class Word(BaseModel):
    i: int = Field(ge=0)
    text: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    speaker: str | None
    confidence: float = Field(ge=0, le=1)
    is_disfluency: bool

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def check_order(self) -> Self:
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must not be before start_ms")
        return self


class Transcript(BaseModel):
    provider: str
    provider_ref: str
    language: str
    duration_ms: int = Field(ge=0)
    text: str
    words: list[Word]

    model_config = ConfigDict(frozen=True)


def is_filler_word(text: str) -> bool:
    return text.lower().strip(".,?!") in FILLER_WORDS
