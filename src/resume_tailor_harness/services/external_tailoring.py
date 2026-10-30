"""External authors supply content; the harness owns evidence and review."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlmodel import Session

from resume_tailor_harness.models.profile import ProfileFacts
from resume_tailor_harness.models.resume import ResumeContent
from resume_tailor_harness.models.review import ReviewCritique
from resume_tailor_harness.profile.store import load_facts
from resume_tailor_harness.progress import ProgressReporter
from resume_tailor_harness.render.export import export_job_artifacts
from resume_tailor_harness.services.agents import build_reviewers
from resume_tailor_harness.services.resume_shape import for_rendering
from resume_tailor_harness.tailor.numeric_evidence import numeric_evidence_critique
from resume_tailor_harness.tailor.panel import run_panel
from resume_tailor_harness.tailor.provenance import (
    provenance_critique,
    renderable_profile,
)
from resume_tailor_harness.tailor.review_config import load_review_config
from resume_tailor_harness.tailor.skill_naming import skill_naming_critique
from resume_tailor_harness.tailor.style_guide import load_style_guide
from resume_tailor_harness.tailor.verdict import aggregate
from resume_tailor_harness.tenancy.paths import REVIEW_PATH
from resume_tailor_harness.tracking.repository import get_job, next_resume_attempt
from resume_tailor_harness.tracking.stages import advance
from resume_tailor_harness.tracking.tables import Job, JobStatus, ResumeVersion


class ExternalTailoringError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def load_context(
    session: Session, job_id: int, facts_path: Path
) -> tuple[Job, ProfileFacts, str]:
    job = get_job(session, job_id)
    if job is None:
        raise ExternalTailoringError("NOT_FOUND", "Job not found")
    if not facts_path.is_file():
        raise ExternalTailoringError(
            "PROFILE_REQUIRED", "Build a profile before tailoring"
        )
    facts = load_facts(facts_path)
    snapshot = {
        "jobId": job_id,
        "jdText": job.jd_text,
        "company": job.company,
        "title": job.title,
        "profile": facts.model_dump(mode="json"),
    }
    revision = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return job, facts, revision


def authoring_context(session: Session, job_id: int, facts_path: Path) -> dict:
    job, facts, revision = load_context(session, job_id, facts_path)
    config = for_rendering(load_review_config(REVIEW_PATH))
    return {
        "jobId": job_id,
        "company": job.company,
        "title": job.title,
        "jdText": job.jd_text,
        "contextRevision": revision,
        "profile": renderable_profile(facts).model_dump(mode="json"),
        "resumeSchema": ResumeContent.model_json_schema(),
        "lengthBudget": config.length_budget.model_dump(mode="json"),
        "styleGuide": load_style_guide(config.style_guide_path),
    }


def deterministic_checks(
    content: ResumeContent, facts: ProfileFacts
) -> list[ReviewCritique]:
    # Identity and credentials have no per-claim citations: preserve them exactly.
    if content.contact != facts.contact:
        raise ExternalTailoringError(
            "IDENTITY_MISMATCH", "Carry profile contact verbatim"
        )
    if any(item not in facts.education for item in content.education):
        raise ExternalTailoringError(
            "IDENTITY_MISMATCH", "Carry education entries verbatim"
        )
    if any(item not in facts.languages for item in content.languages):
        raise ExternalTailoringError(
            "IDENTITY_MISMATCH", "Carry language entries verbatim"
        )
    return [
        provenance_critique(content, facts),
        skill_naming_critique(content, facts),
        numeric_evidence_critique(content, facts),
    ]


def validate_draft(
    session: Session,
    job_id: int,
    facts_path: Path,
    content: ResumeContent,
    context_revision: str,
) -> dict[str, Any]:
    _, facts, revision = load_context(session, job_id, facts_path)
    if revision != context_revision:
        raise ExternalTailoringError(
            "CONTEXT_STALE", "Fetch fresh context and rebase the draft"
        )
    critiques = deterministic_checks(content, facts)
    return {
        "valid": all(c.passed for c in critiques),
        "contextRevision": revision,
        "critiques": [c.model_dump(mode="json") for c in critiques],
    }


def submit_draft(
    session: Session,
    job_id: int,
    facts_path: Path,
    content: ResumeContent,
    context_revision: str,
    agent: str,
    *,
    reporter: ProgressReporter | None = None,
) -> dict[str, Any]:
    job, facts, revision = load_context(session, job_id, facts_path)
    if revision != context_revision:
        raise ExternalTailoringError(
            "CONTEXT_STALE", "Fetch fresh context and rebase the draft"
        )
    critiques = deterministic_checks(content, facts)
    config = for_rendering(load_review_config(REVIEW_PATH))
    if not any(r.name == "fact-check" and r.gate for r in config.reviewers):
        raise ExternalTailoringError(
            "REVIEW_REQUIRED",
            "Enable the fact-check gate before submitting external drafts",
        )
    if all(c.passed for c in critiques):
        reviewers = build_reviewers(
            config, style_guide=load_style_guide(config.style_guide_path)
        )
        critiques.extend(run_panel(content, facts, job.jd_text, config, reviewers))
    verdict = aggregate(critiques, config)
    result: dict[str, Any] = {
        "passed": verdict.passed,
        "versionId": None,
        "verdict": verdict.model_dump(mode="json"),
    }
    if not verdict.passed:
        return result
    if reporter is not None:
        reporter.checkpoint()
    # Review can take minutes. Reject a draft reviewed against superseded evidence.
    session.expire_all()
    job, _, current_revision = load_context(session, job_id, facts_path)
    if current_revision != revision:
        raise ExternalTailoringError(
            "CONTEXT_STALE", "Evidence changed during review; fetch fresh context"
        )
    attempt = next_resume_attempt(session, job_id)
    version = ResumeVersion(
        job_id=job_id,
        round=1,
        attempt=attempt,
        origin="external",
        tailor_model=agent,
        content_json=content.model_dump(mode="json"),
        review_score=verdict.aggregate_score,
        fact_check_passed=verdict.gate_passed,
        critique_json=[c.model_dump(mode="json") for c in critiques],
        gate_reviewers_json=sorted(r.name for r in config.reviewers if r.gate),
    )
    advance(job, JobStatus.tailored.value, never_regress=True)
    session.add(job)
    session.add(version)
    session.commit()
    session.refresh(version)
    export_job_artifacts(session, job_id)
    result["versionId"] = version.id
    return result
