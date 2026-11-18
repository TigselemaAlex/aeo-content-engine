FILLER_WORDS = frozenset({"um", "umm", "uh", "uhm", "hmm", "er", "erm"})


def is_filler_word(text: str) -> bool:
    return text.lower().strip(".,?!") in FILLER_WORDS
