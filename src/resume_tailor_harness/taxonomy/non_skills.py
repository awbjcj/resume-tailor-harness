"""Conservative cleanup suggestions for requirements misfiled as skills.

These rules only propose entries for review. They never remove source job text,
infer a replacement skill, or retire an entry without an explicit mutation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from resume_tailor_harness.taxonomy.snapshot import EffectiveTaxonomy
from resume_tailor_harness.tracking.match_gap import normalize_skill

_DURATION = re.compile(
    r"^(?:(?:at least|minimum(?: of)?|over|more than) )?"
    r"(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty)"
    r"(?: ?(?:to| ) ?\d+)?\+? (?:years|year(?= of\b| experience\b|$)|yrs?|yoe)\b"
)
_DEGREE = re.compile(
    r"\b(?:bachelor(?: s|s)?|master(?: s|s)?|associate(?: s|s)?|doctoral) degree\b"
    r"|^(?:ph\.?d\.?|doctorate)(?: in\b|$)"
    r"|^(?:computer science|computer engineering|electrical engineering|mechanical engineering|"
    r"hard science|life sciences|computational|college|university|stem|advanced) degree\b"
)
_ELIGIBILITY = re.compile(
    r"^(?:(?:active|current|federal|u\.?s\.?|us) )?"
    r"(?:(?:top )?secret(?: security)?|security|ts sci) clearance(?: eligibility)?$"
    r"|^(?:u\.?s\.?|us) citizenship$"
    r"|^(?:work authorization|authorized to work(?: in .+)?|visa sponsorship)$"
)
_TRAVEL = re.compile(
    r"^(?:(?:domestic|international|regular) travel|willingness to travel|"
    r"travel(?: internationally| to customer sites| within the united states| up to \d+)?|"
    r"willingness to relocate|relocation required)$"
)


def non_skill_reason(value: str) -> str | None:
    token = normalize_skill(value)
    if _DURATION.search(token):
        return "Years-of-experience requirement"
    if _DEGREE.search(token):
        return "Education or degree requirement"
    if _ELIGIBILITY.search(token):
        return "Employment eligibility or clearance requirement"
    if _TRAVEL.search(token):
        return "Travel or relocation requirement"
    return None


def cleanup_candidates(
    taxonomy: EffectiveTaxonomy, tokens: Iterable[str] = ()
) -> list[dict[str, str]]:
    """Include saved, already assigned entries as well as current job demand.

    Judge the canonical itself, not an incidental alias: an old bad synonym
    merge must not nominate a valid skill such as computer science for removal.
    """
    cmap = taxonomy.cluster_map
    known = (
        set(tokens) | set(cmap.aliases) | set(cmap.aliases.values())
        | set(cmap.domain_of) | set(taxonomy.corrections.added_skills)
    )
    excluded = taxonomy.retired_keys | {
        cmap.aliases.get(token, token) for token in taxonomy.corrections.removed_skills
    }
    canonicals = {
        cmap.aliases.get(token, token)
        for raw in known if (token := normalize_skill(raw))
    }
    return [
        {"key": key, "reason": reason}
        for key in sorted(canonicals - excluded)
        if (reason := non_skill_reason(key))
    ]
