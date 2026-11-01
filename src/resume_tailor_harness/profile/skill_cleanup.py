"""Deterministic profile cleanup; source documents and non-skill facts are untouched."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from pydantic import Field

from resume_tailor_harness.models.base import ExtensibleModel
from resume_tailor_harness.models.profile import ProfileFacts, Skill
from resume_tailor_harness.profile.manual_skills import (
    ManualSkillsLedger,
    ManualSuppressEntry,
)
from resume_tailor_harness.taxonomy.non_skills import non_skill_reason
from resume_tailor_harness.tracking.match_gap import normalize_skill


class SkillMerge(ExtensibleModel):
    into: str
    names: list[str]


class SkillPrune(ExtensibleModel):
    token: str
    display: str
    reason: str


class CleanupReport(ExtensibleModel):
    enabled: bool = True
    before_count: int = 0
    after_count: int = 0
    merges: list[SkillMerge] = Field(default_factory=list)
    pruned: list[SkillPrune] = Field(default_factory=list)


def merge_skill_records(skills: list[Skill], target: Skill) -> Skill:
    """Keep the target identity, all names, provenance and supporting evidence."""
    merged = target.model_copy(deep=True)
    seen = {normalize_skill(target.name)}
    aliases: list[str] = []
    for skill in skills:
        for name in (skill.name, *skill.aliases):
            token = normalize_skill(name)
            if token and token not in seen:
                aliases.append(name.strip())
                seen.add(token)
    merged.aliases = aliases
    merged.evidence_fact_ids = list(
        dict.fromkeys(fid for s in skills for fid in s.evidence_fact_ids)
    )
    merged.inferred = all(s.inferred for s in skills)
    # Keep every original source pointer without turning inferred evidence into a claim.
    merged.source_refs = sorted(
        {ref for s in skills for ref in [s.source_ref, *s.source_refs] if ref}
    )
    merged.context = (
        "\n".join(dict.fromkeys(s.context for s in skills if s.context)) or None
    )
    return merged


def clean_skills(
    facts: ProfileFacts,
    ledger: ManualSkillsLedger,
    *,
    aliases: dict[str, str] | None = None,
    forbid_alias: Sequence[Sequence[str]] = (),
    added_at: str = "",
) -> tuple[ProfileFacts, CleanupReport]:
    """Merge exact/saved synonyms; retire only conservative non-skill patterns.

    No fuzzy spelling, popularity cutoff or evidence-count threshold can delete a
    distinct skill. Restored entries are exempt from subsequent automatic pruning.
    """
    output = facts.model_copy(deep=True)
    records = [(bucket, s) for bucket, skills in output.skills.items() for s in skills]
    report = CleanupReport(enabled=ledger.auto_cleanup, before_count=len(records))
    alias_map = aliases or {}
    parents: dict[str, str] = {}
    forbidden = [
        (normalize_skill(pair[0]), normalize_skill(pair[1]))
        for pair in forbid_alias
        if len(pair) == 2
    ]

    def identity(name: str) -> str:
        return normalize_skill(name) or "literal:" + name.casefold().strip()

    def root(token: str) -> str:
        parents.setdefault(token, token)
        while parents[token] != token:
            parents[token] = parents[parents[token]]
            token = parents[token]
        return token

    def union(first: str, second: str) -> None:
        left, right = root(first), root(second)
        if left == right:
            return
        if any(
            {root(a), root(b)} == {left, right}
            for a, b in forbidden
            if a and b and a != b
        ):
            return
        parents[left] = right

    for _, skill in records:
        tokens = [identity(n) for n in (skill.name, *skill.aliases)]
        tokens = [t for t in tokens if t]
        for token in tokens:
            head = alias_map.get(token, token)
            union(token, head)
        for token in tokens[1:]:
            # Explicitly separated saved canonicals (including forbid_alias
            # corrections) win over an older source's ambiguous alias list.
            if (
                tokens[0] in alias_map
                and token in alias_map
                and alias_map[tokens[0]] != alias_map[token]
            ):
                continue
            union(token, tokens[0])

    grouped: dict[str, list[tuple[str, Skill]]] = defaultdict(list)
    for bucket, skill in records:
        token = identity(skill.name)
        grouped[root(token)].append((bucket, skill))
    output.skills = {}
    exempt = set(map(normalize_skill, ledger.cleanup_exempt))
    remapped_ids: dict[str, str] = {}
    for members in grouped.values():
        # Literal evidence wins over inferred evidence; prefer a saved canonical name.
        bucket, target = min(
            members,
            key=lambda item: (
                item[1].inferred,
                alias_map.get(
                    normalize_skill(item[1].name), normalize_skill(item[1].name)
                )
                != normalize_skill(item[1].name),
                -len(item[1].evidence_fact_ids),
            ),
        )
        skills = [s for _, s in members]
        merged = merge_skill_records(skills, target) if len(skills) > 1 else target
        remapped_ids.update({skill.id: target.id for skill in skills})
        if len(skills) > 1:
            report.merges.append(
                SkillMerge(into=target.name, names=[s.name for s in skills])
            )
        token = normalize_skill(merged.name)
        reason = (
            non_skill_reason(merged.name)
            if not any(normalize_skill(s.name) in exempt for s in skills)
            else None
        )
        if not merged.name.strip():
            reason = "Empty skill name"
        if reason:
            ledger.entries.append(
                ManualSuppressEntry(
                    token=token,
                    display=merged.name,
                    skills=skills,
                    reason=reason,
                    added_at=added_at,
                )
            )
            report.pruned.append(
                SkillPrune(token=token, display=merged.name, reason=reason)
            )
        else:
            output.skills.setdefault(bucket, []).append(merged)
    for bucket in output.skills.values():
        for skill in bucket:
            skill.evidence_fact_ids = list(
                dict.fromkeys(
                    remapped_ids.get(fid, fid) for fid in skill.evidence_fact_ids
                )
            )
    report.after_count = sum(map(len, output.skills.values()))
    return output, report
