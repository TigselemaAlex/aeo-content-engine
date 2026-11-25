"""Ingest rules about transcript words: which words count as fillers.

Pure code (no network, disk or subprocess). The list lives in `ingest`, not in
`shared`, because deciding what a filler is belongs to this module (docs/06 §5.2).
"""

FILLER_WORDS = frozenset({"um", "umm", "uh", "uhm", "hmm", "er", "erm"})
"""Lowercase filler words that `is_filler_word` matches.

The entries are examples of the usual English fillers: "um" and "uh" with their
spellings "umm" and "uhm", plus "hmm", "er" and "erm". The list is not complete
and can be extended with other fillers.

The worker keeps its own list because AssemblyAI keeps fillers in the transcript
but does not mark them (decision "Muletillas y glosario", docs/00). "uh-huh" and
"mhm" are left out on purpose: they are usually answers, not fillers (docs/00).
"""


def is_filler_word(text: str) -> bool:
    """Return whether a transcribed word is a filler such as "um" or "uh".

    The word is lowercased and spaces and the characters `.`, `,`, `?`, `!` and `-`
    are removed from both ends only. The provider writes punctuation inside the word
    (`"um,"`) and ends a word cut off mid-way with a hyphen (the test transcript has
    `"haven't-"`), so a cut-off filler such as `"uh-"` still counts. A hyphen in the
    middle stays, so `"Uh-huh"` is not a filler. Then the word must equal one entry
    of `FILLER_WORDS`: a word that only starts like a filler ("umbrella") is not one.
    The transcription adapter uses it to set `Word.is_disfluency` (docs/03 §3).

    Args:
        text: One word as the provider wrote it, punctuation included.

    Returns:
        True if the cleaned word is in `FILLER_WORDS`, False otherwise.

    Example:
        >>> is_filler_word("Um,")
        True
        >>> is_filler_word("uh-")
        True
        >>> is_filler_word("umbrella")
        False
        >>> is_filler_word("Uh-huh")
        False
        >>> is_filler_word("haven't-")
        False
    """
    return text.lower().strip(" .,?!-") in FILLER_WORDS
