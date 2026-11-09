"""Generate and cache evidence-grounded gap-closing suggestions."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any, Callable, Literal
from urllib.parse import urlsplit, urlunsplit

from sqlmodel import Session, select

from resume_tailor_harness.github.repos import RepoMeta, parse_github_url
from resume_tailor_harness.llm_runner import expect_schema, expect_text
from resume_tailor_harness.models.profile import ProfileFacts
from resume_tailor_harness.suggestions.agents import SuggestionDraft
from resume_tailor_harness.tracking.match_gap import DemandGraph, profile_skill_tokens
from resume_tailor_harness.tracking.tables import SkillSuggestion, utcnow

SuggestionKind = Literal["skill", "domain"]
RepoVerifier = Callable[[str, str], RepoMeta | None]
_SQLITE_SUGGESTION_WRITE_LOCK = Lock()


class SuggestionTargetNotFound(ValueError):
    def __init__(self, kind: str, key: str) -> None:
        super().__init__(f"unknown {kind} suggestion target: {key}")


class SuggestionTargetChanged(ValueError):
    def __init__(self) -> None:
        super().__init__(
            "This roadmap has changed. Reload the learning library before regenerating."
        )


@dataclass(frozen=True)
class SuggestionContext:
    kind: SuggestionKind
    key: str
    label: str
    members: tuple[str, ...]
    demanding_job_ids: tuple[int, ...]
    jobs_context: str


@dataclass(frozen=True)
class SuggestionStatus:
    kind: SuggestionKind
    key: str
    state: Literal["ready", "stale"]
    generated_at: datetime


def resolve_suggestion_context(
    graph: DemandGraph,
    *,
    kind: SuggestionKind,
    key: str,
) -> SuggestionContext:
    if kind == "skill":
        skill = next(
            (
                candidate
                for candidate in graph.skills
                if candidate.key == key
                or candidate.skill == key
                or key in candidate.members
            ),
            None,
        )
        if skill is None:
            raise SuggestionTargetNotFound(kind, key)
        label = skill.skill
        canonical_key = skill.key
        members = tuple(sorted(skill.members, key=lambda item: (item.casefold(), item)))
        edge_keys = {skill.key}
    else:
        theme = next(
            (candidate for candidate in graph.domains if candidate.id == key), None
        )
        if theme is None:
            raise SuggestionTargetNotFound(kind, key)
        label = theme.label
        canonical_key = theme.id
        members = tuple(
            sorted(skill.key for skill in graph.skills if skill.domain_id == theme.id)
        )
        edge_keys = set(members)

    job_ids = tuple(
        sorted(
            {
                edge.job_id
                for edge in graph.edges
                if (edge.skill_key or edge.skill) in edge_keys
            }
        )
    )
    jobs_by_id = {job.id: job for job in graph.jobs}
    jobs_context = "; ".join(
        f"{jobs_by_id[job_id].company or 'Unknown company'} — "
        f"{jobs_by_id[job_id].title or 'Untitled role'}"
        for job_id in job_ids
        if job_id in jobs_by_id
    )
    return SuggestionContext(kind, canonical_key, label, members, job_ids, jobs_context)


def find_suggestion_row(
    session: Session,
    context: SuggestionContext,
) -> SkillSuggestion | None:
    rows = session.exec(
        select(SkillSuggestion).where(SkillSuggestion.kind == context.kind)
    ).all()
    return select_suggestion_row({(row.kind, row.key): row for row in rows}, context)


def select_suggestion_row(
    rows: Mapping[tuple[str, str], SkillSuggestion], context: SuggestionContext
) -> SkillSuggestion | None:
    """Choose the same persisted roadmap for reads, generation, and the library."""
    canonical = rows.get((context.kind, context.key))
    if canonical is not None or context.kind == "domain":
        return canonical
    legacy_keys = {context.label, *context.members}
    return next(
        (
            rows[(context.kind, key)]
            for key in sorted(legacy_keys)
            if (context.kind, key) in rows
        ),
        None,
    )


def require_roadmap_target(
    session: Session, context: SuggestionContext, expected_roadmap_id: int
) -> None:
    row = find_suggestion_row(session, context)
    if row is None or row.id != expected_roadmap_id:
        raise SuggestionTargetChanged()


def suggestion_statuses(
    session: Session,
    graph: DemandGraph,
    coverage: set[str],
) -> list[SuggestionStatus]:
    purge_legacy_theme_suggestions(session)
    contexts: dict[tuple[SuggestionKind, str], SuggestionContext] = {}
    rows = session.exec(select(SkillSuggestion)).all()
    rows_by_key = {(row.kind, row.key): row for row in rows}
    for row in rows:
        if row.kind not in ("skill", "domain"):
            continue
        kind: SuggestionKind = row.kind
        try:
            context = resolve_suggestion_context(graph, kind=kind, key=row.key)
        except SuggestionTargetNotFound:
            continue
        contexts[(kind, context.key)] = context

    selected = {
        identity: (row, context)
        for identity, context in contexts.items()
        if (row := select_suggestion_row(rows_by_key, context)) is not None
    }

    return [
        SuggestionStatus(
            kind=kind,
            key=key,
            state=(
                "ready"
                if row.fingerprint == suggestion_fingerprint(context, coverage)
                else "stale"
            ),
            generated_at=row.generated_at,
        )
        for (kind, key), (row, context) in sorted(selected.items())
    ]


def purge_legacy_theme_suggestions(session: Session) -> int:
    """Delete pre-taxonomy suggestion rows whose theme keys are now orphaned."""
    rows = session.exec(
        select(SkillSuggestion).where(SkillSuggestion.kind == "theme")
    ).all()
    for row in rows:
        session.delete(row)
    if rows:
        session.commit()
    return len(rows)


def suggestion_fingerprint(
    context: SuggestionContext,
    coverage: set[str],
    schema_version: int = 1,
) -> str:
    payload = json.dumps(
        {
            "schema_version": schema_version,
            "kind": context.kind,
            "key": context.key,
            "coverage": sorted(coverage),
            "members": sorted(context.members),
            "demanding_job_ids": sorted(context.demanding_job_ids),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


_URL = re.compile(r"https?://[^\s<>\]\[()]+")


def _normalized_http_url(value: str) -> str | None:
    parsed = urlsplit(value.rstrip(".,;:"))
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, "")
    )


def _verified_repos(
    draft: SuggestionDraft,
    verify: RepoVerifier,
    evidence_urls: set[str],
) -> list[dict[str, Any]]:
    repositories: list[dict[str, Any]] = []
    seen: set[str] = set()
    for reference in draft.repos:
        normalized = _normalized_http_url(reference.url)
        if normalized is None or normalized not in evidence_urls:
            continue
        parsed = parse_github_url(reference.url)
        if parsed is None:
            continue
        metadata = verify(*parsed)
        if metadata is None or metadata.full_name in seen:
            continue
        seen.add(metadata.full_name)
        repositories.append(
            {
                "name": metadata.full_name,
                "url": metadata.url,
                "why": reference.why,
                "stars": metadata.stars,
                "description": metadata.description,
            }
        )
    return repositories


def _payload_from_evidence(
    draft: SuggestionDraft,
    research: str,
    verify: RepoVerifier,
) -> dict[str, Any]:
    evidence_urls = {
        normalized
        for raw_url in _URL.findall(research)
        if (normalized := _normalized_http_url(raw_url)) is not None
    }
    project = None
    if draft.project is not None:
        project = {
            "title": draft.project.title,
            "summary": draft.project.summary,
            "skills_demonstrated": draft.project.skills_demonstrated,
        }

    payload = {
        "repos": _verified_repos(draft, verify, evidence_urls),
        "resources": [
            {"title": resource.title, "url": normalized, "kind": resource.kind}
            for resource in draft.resources
            if (normalized := _normalized_http_url(resource.url)) in evidence_urls
        ],
        "project": project,
        "bridge": draft.bridge.strip(),
        "citations": sorted(evidence_urls),
    }
    if not (
        payload["repos"]
        or payload["resources"]
        or payload["project"]
        or payload["bridge"]
    ):
        raise ValueError("advisor formatter returned an empty suggestion")
    return payload


def _search_prompt(context: SuggestionContext) -> str:
    if context.kind == "domain":
        return (
            f"Theme gap: {context.label}. Member skills: {', '.join(context.members)}.\n"
            f"Jobs demanding these skills: {context.jobs_context}\n"
            "Research a learning path that closes this capability gap."
        )
    return (
        f"Skill gap: {context.label}.\n"
        f"Jobs demanding it: {context.jobs_context}\n"
        "Research real repositories, official learning resources, and a portfolio project."
    )


def _format_prompt(research: str, coverage: set[str]) -> str:
    bridge_context = ", ".join(sorted(coverage)) or "(no profile skills on file)"
    return (
        f"Research:\n{research}\n\n"
        f"Profile skills available for bridge framing:\n{bridge_context}"
    )


def generate_suggestion(
    session: Session,
    *,
    context: SuggestionContext,
    search_agent,
    formatter,
    verify: RepoVerifier,
    facts: ProfileFacts,
    reporter=None,
    expected_roadmap_id: int | None = None,
) -> SkillSuggestion:
    coverage = profile_skill_tokens(facts)
    research = expect_text(
        search_agent.run(_search_prompt(context)), source="suggestions-research"
    )
    if reporter is not None:
        reporter.checkpoint()
    formatted = expect_schema(
        formatter.run(_format_prompt(research, coverage)),
        SuggestionDraft,
        source="suggestions-formatter",
    )
    if reporter is not None:
        reporter.checkpoint()

    payload = _payload_from_evidence(formatted, research, verify)
    fingerprint = suggestion_fingerprint(context, coverage)
    # Suggestion research runs concurrently, but SQLite allows only one writer.
    # Keep the lock around the short persistence phase, never the network/LLM work.
    with _SQLITE_SUGGESTION_WRITE_LOCK:
        row = find_suggestion_row(session, context)
        if expected_roadmap_id is not None and (
            row is None or row.id != expected_roadmap_id
        ):
            raise SuggestionTargetChanged()
        if row is None:
            row = SkillSuggestion(kind=context.kind, key=context.key)
            session.add(row)
        else:
            row.key = context.key
        row.payload_json = payload
        row.fingerprint = fingerprint
        row.generated_at = utcnow()
        session.commit()
        session.refresh(row)
    return row
