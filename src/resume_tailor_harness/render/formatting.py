"""Presentation rules shared by resume exports and visual review."""

import re
from datetime import date

from resume_tailor_harness.models.resume import ResumeContent, TailoredSkill

_MINOR_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "but",
        "by",
        "for",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)
_MONTH_NAMES = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_MONTH_ABBR = tuple(name[:3] for name in _MONTH_NAMES)
_MONTHS = {
    name.casefold(): month
    for names in (_MONTH_NAMES, _MONTH_ABBR)
    for month, name in enumerate(names)
    if name
} | {"sept": 9}


def format_label(value: str) -> str:
    """Title-case role/category labels, retaining acronyms and mixed-case names."""
    words = value.split()
    for index, word in enumerate(words):
        if index and word.strip("()[]{}:;,.").casefold() in _MINOR_WORDS:
            words[index] = word.lower()
        elif word.islower():
            # Work per token so Node.js, iOS, eBay, OpenAI and API-based keep
            # their original spelling instead of being damaged by str.title().
            words[index] = re.sub(
                r"(^|[-/—–(\[{])([^\W\d_])",
                lambda match: match[1] + match[2].upper(),
                word,
            ).replace("Co-Op", "Co-op")
    return " ".join(words)


def _formatted_date(year: int, month: int, day: int | None = None) -> str | None:
    try:
        date(year, month, day if day is not None else 1)
    except ValueError:
        return None
    name = _MONTH_ABBR[month]
    return f"{name} {day}, {year}" if day is not None else f"{name} {year}"


def format_date(value: str | None) -> str | None:
    """Normalize known date spellings without guessing or discarding precision."""
    if value is None:
        return None
    text = " ".join(value.split())
    if text.casefold() in {"present", "current", "ongoing"}:
        return "Present"
    if match := re.fullmatch(r"(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?", text):
        return (
            _formatted_date(
                int(match[1]), int(match[2]), int(match[3]) if match[3] else None
            )
            or text
        )
    if match := re.fullmatch(r"([A-Za-z]+)\.?\s+(?:(\d{1,2}),?\s+)?(\d{4})", text):
        if month := _MONTHS.get(match[1].casefold()):
            return (
                _formatted_date(
                    int(match[3]), month, int(match[2]) if match[2] else None
                )
                or text
            )
    if match := re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})", text):
        if month := _MONTHS.get(match[2].casefold()):
            return _formatted_date(int(match[3]), month, int(match[1])) or text
    return text


def format_resume_metadata(content: ResumeContent) -> ResumeContent:
    """Format a display copy; saved content and evidence remain untouched."""
    rendered = content.model_copy(deep=True)
    for experience in rendered.experience:
        experience.title = format_label(experience.title)
    for project in (*rendered.projects, *rendered.portfolio):
        if project.role is not None:
            project.role = format_label(project.role)
    for volunteer in rendered.volunteer:
        if volunteer.role is not None:
            volunteer.role = format_label(volunteer.role)
    for record in (
        *rendered.experience,
        *rendered.projects,
        *rendered.portfolio,
        *rendered.education,
        *rendered.volunteer,
    ):
        record.start = format_date(record.start)
        record.end = format_date(record.end)
    for dated in (*rendered.publications, *rendered.certifications, *rendered.awards):
        dated.date = format_date(dated.date)
    for section in rendered.additional_sections:
        for entry in section.entries:
            entry.date = format_date(entry.date)

    skills: dict[str, list[TailoredSkill]] = {}
    for category, entries in rendered.skills.items():
        # Differently cased labels can converge. Keep every skill and citation
        # rather than silently overwriting an earlier category.
        skills.setdefault(format_label(category), []).extend(entries)
    rendered.skills = skills
    return rendered
