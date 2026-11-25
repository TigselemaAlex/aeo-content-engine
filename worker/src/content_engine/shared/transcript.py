"""Word-level transcript of the original video, shared by every module that reads it.

Times are milliseconds on the clock of the original (uploaded) video's audio track,
where 0 ms is its first sample. Words are addressed by their index `i`, the common
language of `ingest`, the clip timeline and the other pieces (docs/06 §5.2,
decision "Transcripción como núcleo compartido" in docs/00).
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Word(BaseModel):
    """One transcribed word with its timing, speaker and filler flag.

    Matches one item of `transcripts.words` (docs/02 §4.3). The model is frozen:
    a word cannot be changed after it is built.

    Attributes:
        i: Position of the word in `Transcript.words`, 0 or more. Claude and the
            clip timeline refer to words by this index, never by milliseconds.
        text: The word as the provider wrote it, punctuation included (for
            example `"um,"`).
        start_ms: Start of the word, in ms of the original video, 0 or more.
        end_ms: End of the word, in ms of the original video, 0 or more and not
            before `start_ms`.
        speaker: Speaker label from the provider (`"A"`, `"B"`...), or `None` if
            the provider gave none.
        confidence: Provider confidence that the word is right, from 0 to 1.
            Misheard words come out low: "AIO" instead of "AEO" scored 0.33 in
            T1.4 (docs/00, decision "Muletillas y glosario").
        is_disfluency: Whether the word is a filler ("um", "uh"). The provider
            does not mark it; the adapter sets it with `is_filler_word` from
            `modules/ingest/domain` (docs/03 §3).

    Raises:
        pydantic.ValidationError: If a field breaks its limits or `end_ms` is
            before `start_ms`.
    """

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
        """Reject a word whose `end_ms` is before its `start_ms`.

        Pydantic runs this after checking each field. A word with
        `start_ms == end_ms` is accepted.

        Returns:
            The same word, unchanged.

        Raises:
            ValueError: If `end_ms` is before `start_ms`. Pydantic reports it to
                the caller as a `pydantic.ValidationError`.
        """
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must not be before start_ms")
        return self


class Transcript(BaseModel):
    """Full transcript of the original video, in the worker's own format.

    Built by the transcription adapter from the provider's response, so no other
    code reads the raw response. Matches the `transcripts` table (docs/02 §4.3).
    The model is frozen.

    Attributes:
        provider: Name of the transcription service, for example `"assemblyai"`.
        provider_ref: The provider's id for this transcription, to find it there.
        language: Language code reported by the provider, for example `"en"`.
        duration_ms: Length of the transcribed audio, in ms, 0 or more.
            AssemblyAI gives seconds; its adapter converts `s x 1000 -> ms`,
            rounded to a whole ms.
        text: The whole transcript as one string, punctuation included.
        words: Every word in spoken order. The adapter numbers them so that
            `words[k].i == k`; this model does not check it.
    """

    provider: str
    provider_ref: str
    language: str
    duration_ms: int = Field(ge=0)
    text: str
    words: list[Word]

    model_config = ConfigDict(frozen=True)
