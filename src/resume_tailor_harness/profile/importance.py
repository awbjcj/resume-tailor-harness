"""Deterministic, explainable importance scores independent of a target job.

Scoring copies its input. Neither scoring nor ranking changes claim text, ids,
provenance, source order, or the fact-lock eligibility of inferred skills.
"""

from resume_tailor_harness.models.base import FactItem
from resume_tailor_harness.models.importance import (
    FactContext,
    FactImportanceScore,
    FactImportanceSignals,
)
from resume_tailor_harness.models.profile import (
    Bullet,
    Education,
    Experience,
    ProfileFacts,
    Project,
    Volunteer,
)


IMPORTANCE_WEIGHTS = {
    "significance": 25,
    "essentiality": 20,
    "context": 20,
    "impact": 15,
    "ownership": 10,
    "evidence": 10,
}
CONTEXT_SCORES: dict[FactContext, int] = {
    "professional": 100,
    "research": 80,
    "personal_project": 65,
    "academic_project": 55,
    "education": 60,
    "volunteer": 60,
    "unknown": 50,
}

# Shared by extractors so their assessments use the same scale and boundaries.
IMPORTANCE_INSTRUCTIONS = (
    "For each fact, populate importance as selection metadata, never as a new claim. "
    "Rate significance and essentiality from 0 (incidental/dispensable), 1 (supporting), "
    "2 (useful), 3 (major/core), to 4 (defining/indispensable to understanding this "
    "experience). Significance measures achievement or scope; essentiality measures "
    "whether removing this fact would hide the core responsibility, contribution or "
    "qualification. Rate impact 0 when unstated, 1 for an activity/deliverable, 2 for "
    "an explicit qualitative result, 3 for a measured result with scope, and 4 for a "
    "major measured result with baseline or comparison. Rate ownership 0 when "
    "unstated, 1 for participation, 2 for a specific personal contribution, 3 for "
    "explicit ownership/leadership, and 4 for explicit end-to-end accountability. "
    "Use only source-supported context: professional (employment/internship/client "
    "work), personal_project, academic_project (course/capstone), research, education, "
    "volunteer, or unknown. A GitHub repository, technical complexity, or a dossier "
    "alone proves neither personal authorship nor paid work. Do not guess context, "
    "outcomes or ownership. Keep importance_score null; the application computes it. "
    "Preserve every supported fact regardless of its rating. Missing metrics never "
    "authorize estimates, arithmetic, new numbers, or rewriting source claims."
)
IMPORTANCE_SELECTION_INSTRUCTION = (
    "Use importance_score.score (0-100) and its components to prioritize equally "
    "job-relevant facts and allocate more distinct evidence to stronger experiences. "
    "Direct required-skill coverage comes first; a relevant strong school/personal "
    "project can outrank weaker work. Lead each owner's bullets with its strongest "
    "relevant facts. Emphasize core capabilities naturally in summary, skills and "
    "supporting experience, without repeating the same claim or stuffing keywords. "
    "An importance score is selection metadata, never proof of a claim, ownership, "
    "or eligibility. Keep employment in reverse chronological order."
)


def _fallback_signals(fact: FactItem) -> FactImportanceSignals:
    if isinstance(fact, Bullet):
        major = fact.aspect in {"scope", "technical", "impact", "leadership", "problem"}
        return FactImportanceSignals(
            significance=3 if major else 2,
            essentiality=3 if fact.aspect in {"scope", "impact", "leadership"} else 2,
            impact=2 if fact.aspect == "impact" else 0,
            # An aspect is not evidence of sole ownership or accountability.
            ownership=1 if fact.aspect == "leadership" else 0,
        )
    if isinstance(fact, (Experience, Project)):
        children = fact.bullets if isinstance(fact, Experience) else fact.highlights
        signals = [child.importance or _fallback_signals(child) for child in children]
        return FactImportanceSignals(
            significance=max([2, *(item.significance for item in signals)]),
            essentiality=max([3, *(item.essentiality for item in signals)]),
            impact=max([0, *(item.impact for item in signals)]),
            ownership=max([0, *(item.ownership for item in signals)]),
        )
    return FactImportanceSignals(essentiality=3 if isinstance(fact, Education) else 2)


def _score(
    fact: FactItem,
    context: FactContext = "unknown",
    *,
    source_ref: str | None = None,
    evidence: float | None = None,
) -> None:
    signals = fact.importance or _fallback_signals(fact)
    if isinstance(fact, (Experience, Project)):
        # Dossier metadata is extracted before its complete evidence bank is
        # restored. Let that evidence inform the owner without a count bonus.
        children = fact.bullets if isinstance(fact, Experience) else fact.highlights
        child_signals = [
            child.importance or _fallback_signals(child) for child in children
        ]
        signals = signals.model_copy(
            update={
                name: max(
                    [
                        getattr(signals, name),
                        *(getattr(item, name) for item in child_signals),
                    ]
                )
                for name in ("significance", "essentiality", "impact", "ownership")
            }
        )
    if context == "unknown":
        context = signals.context
    values = {
        "significance": signals.significance * 25,
        "essentiality": signals.essentiality * 25,
        "context": CONTEXT_SCORES[context],
        "impact": signals.impact * 25,
        "ownership": signals.ownership * 25,
        # Traceability, not a claim that the underlying source is true.
        "evidence": evidence
        if evidence is not None
        else (75 if fact.source_ref or source_ref else 50),
    }
    components = {
        name: round(weight * values[name] / 100, 2)
        for name, weight in IMPORTANCE_WEIGHTS.items()
    }
    fact.importance_score = FactImportanceScore(
        score=round(sum(components.values()), 2),
        context=context,
        method="assessed" if fact.importance is not None else "fallback",
        components=components,
    )


def score_profile(facts: ProfileFacts) -> ProfileFacts:
    """Score every addressable fact, including legacy and inferred records.

    An owner supplies context to its bullets. Skill pointers inherit context
    only from resolved literal evidence. Counts, stars, repeated citations and
    document length never increase importance. Supplied totals are recomputed.
    """
    output = facts.model_copy(deep=True)
    evidence_by_id: dict[str, FactItem] = {}
    for owner in (*output.experience, *output.projects):
        context: FactContext = (
            "professional"
            if isinstance(owner, Experience)
            else owner.importance.context
            if owner.importance
            else "unknown"
        )
        _score(owner, context)
        evidence_by_id[owner.id] = owner
        children = owner.bullets if isinstance(owner, Experience) else owner.highlights
        for bullet in children:
            _score(bullet, context, source_ref=owner.source_ref)
            evidence_by_id[bullet.id] = bullet
    for record in (
        *output.education,
        *output.certifications,
        *output.publications,
        *output.awards,
        *output.languages,
        *output.volunteer,
        *(entry for section in output.additional_sections for entry in section.entries),
        *([output.github_profile] if output.github_profile is not None else []),
    ):
        context = (
            "education"
            if isinstance(record, Education)
            else "volunteer"
            if isinstance(record, Volunteer)
            else "unknown"
        )
        _score(record, context)
        evidence_by_id[record.id] = record
    for entries in output.skills.values():
        for skill in entries:
            supporting = [
                evidence_by_id[fact_id]
                for fact_id in skill.evidence_fact_ids
                if fact_id in evidence_by_id
            ]
            best = max(supporting, key=importance_value, default=None)
            context = (
                best.importance_score.context
                if best is not None and best.importance_score is not None
                else "unknown"
            )
            _score(
                skill,
                context,
                evidence=100
                if supporting
                else 0
                if skill.inferred
                else (75 if skill.source_ref or skill.source_refs else 50),
            )
    return output


def importance_value(fact: FactItem) -> float:
    return fact.importance_score.score if fact.importance_score is not None else 0
