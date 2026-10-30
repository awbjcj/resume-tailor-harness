"""Pure job-description cleanup shared by ingestion, detail, and previews.

Keep cleanup order stable: imported/legacy descriptions are normalized on read
and normalization is not idempotent for every escaped-Markdown input.
"""

import re

_MATERIAL_ICON_TOKENS = frozenset(
    {
        "business_center",
        "corporate_fare",
        "event",
        "laptop_windows",
        "location_on",
        "payments",
        "place",
        "schedule",
        "school",
        "work",
    }
)
_ESCAPED_STRONG = re.compile(r"\\\*\\\*([^*\n]+?)\\\*\\\*")


def _is_icon_character(value: str) -> bool:
    return "a" <= value <= "z" or "0" <= value <= "9"


def _icon_token_at(text: str, start: int, *, escaped: bool) -> tuple[int, str] | None:
    """Return one source-chrome icon token without regex backtracking.

    Google/Material icons are emitted as ``_place_`` or ``\\_place\\_``. The
    former regular expressions had bounded-looking, but nested, repetitions
    that static analysis correctly treats as a potential ReDoS risk on fetched
    job descriptions. This finite scanner preserves the accepted token grammar
    while consuming each character at most once.
    """

    delimiter = "\\_" if escaped else "_"
    if not text.startswith(delimiter, start) or (
        start and not text[start - 1].isspace()
    ):
        return None
    cursor = start + len(delimiter)
    if cursor >= len(text) or not ("a" <= text[cursor] <= "z"):
        return None
    token_start = cursor
    cursor += 1
    while cursor < len(text) and _is_icon_character(text[cursor]):
        cursor += 1

    while text.startswith(delimiter, cursor):
        delimiter_start = cursor
        cursor += len(delimiter)
        if cursor == len(text) or text[cursor].isspace() or text[cursor] in ",.":
            token = text[token_start:delimiter_start].replace("\\_", "_").lower()
            return cursor, token
        if cursor >= len(text) or not _is_icon_character(text[cursor]):
            return None
        while cursor < len(text) and _is_icon_character(text[cursor]):
            cursor += 1
    return None


def _drop_material_icon_tokens(text: str, *, escaped: bool) -> str:
    if ("\\_" if escaped else "_") not in text:
        return text
    kept: list[str] = []
    cursor = 0
    while cursor < len(text):
        token = _icon_token_at(text, cursor, escaped=escaped)
        if token is not None:
            end, name = token
            if name in _MATERIAL_ICON_TOKENS:
                cursor = end
                continue
        kept.append(text[cursor])
        cursor += 1
    return "".join(kept)


def _strip_horizontal_space_before_punctuation(text: str) -> str:
    """Drop spaces and tabs immediately before punctuation in linear time."""
    cleaned: list[str] = []
    for character in text:
        if character in ",.;:":
            while cleaned and cleaned[-1] in " \t":
                cleaned.pop()
        cleaned.append(character)
    return "".join(cleaned)


def clean_job_description_text(text: str) -> str:
    """Remove source chrome tokens that leak into fetched job descriptions."""
    if not text:
        return ""
    cleaned = _drop_material_icon_tokens(text, escaped=True)
    cleaned = _drop_material_icon_tokens(cleaned, escaped=False)
    cleaned = _ESCAPED_STRONG.sub(r"\1", cleaned)
    cleaned = _strip_horizontal_space_before_punctuation(cleaned)
    lines = (re.sub(r"[ \t]{2,}", " ", line).strip() for line in cleaned.splitlines())
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def job_description_preview(text: str) -> str:
    """The first 400 cleaned characters, including legacy description semantics.

    A distant closing Markdown delimiter can affect the beginning of the text,
    so slicing raw input before cleaning is not equivalent.
    """
    return clean_job_description_text(text)[:400]
