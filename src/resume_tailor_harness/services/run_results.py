"""Capture safe result identities once and resolve useful destinations on reads."""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from urllib.parse import urlencode

from sqlmodel import Session, col, select

from resume_tailor_harness.api.schemas.run_completions import RunCompletionOut
from resume_tailor_harness.services.application_continuation import (
    application_next_steps,
)
from resume_tailor_harness.sessions.store import valid_session_id
from resume_tailor_harness.tracking.tables import (
    CoverLetter,
    Job,
    ResumeVersion,
    RunCompletion,
    RunCompletionTarget,
)

_MAX_JOB_TARGETS = 500
SessionExists = Callable[[str, str], bool]


def _existed_at(created_at: datetime, completed_at: datetime) -> bool:
    # SQLite returns naive UTC datetimes. Reused IDs must not make new rows
    # appear to be the result of work that finished before they existed.
    created = (
        created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    )
    completed = (
        completed_at
        if completed_at.tzinfo
        else completed_at.replace(tzinfo=timezone.utc)
    )
    return created <= completed


def _record(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def _positive_id(value: object) -> int | None:
    return value if type(value) is int and 0 < value < 2**63 else None


def _id(data: Mapping[str, object], *keys: str) -> int | None:
    return next(
        (value for key in keys if (value := _positive_id(data.get(key))) is not None),
        None,
    )


def capture_run_target(
    run_id: str, *, meta: object = None, result: object = None
) -> RunCompletionTarget | None:
    """Persist IDs only. Arbitrary metadata, paths, links and tokens are discarded."""
    metadata, output = _record(meta), _record(result)
    job_ids: list[int] = []
    for data in (output, metadata):
        direct = _id(data, "jobId", "job_id")
        if direct is not None:
            job_ids.append(direct)
        raw_ids = data.get("jobIds", data.get("job_ids"))
        if isinstance(raw_ids, list):
            job_ids.extend(
                value
                for raw in raw_ids[:_MAX_JOB_TARGETS]
                if (value := _positive_id(raw)) is not None
            )
    for key in ("jobs", "coverLetters", "outcomes"):
        records = output.get(key)
        if isinstance(records, list):
            job_ids.extend(
                value
                for item in records[:_MAX_JOB_TARGETS]
                if (value := _id(_record(item), "jobId", "job_id")) is not None
            )
    session_id = output.get("sessionId", output.get("session_id")) or metadata.get(
        "sessionId"
    )
    session_id = (
        session_id
        if isinstance(session_id, str) and valid_session_id(session_id)
        else None
    )
    resume_id = _id(output, "versionId", "version_id", "resumeVersionId") or _id(
        metadata, "versionId", "resumeVersionId"
    )
    letter_id = _id(output, "coverLetterId", "cover_letter_id") or _id(
        metadata, "coverLetterId"
    )
    bounded_jobs = list(dict.fromkeys(job_ids))[:_MAX_JOB_TARGETS]
    if not (bounded_jobs or resume_id or letter_id or session_id):
        return None
    return RunCompletionTarget(
        run_id=run_id,
        job_ids_json=bounded_jobs,
        resume_version_id=resume_id,
        cover_letter_id=letter_id,
        session_id=session_id,
    )


def _workspace(kind: str) -> str:
    if kind.startswith("profile-coach-"):
        return "/coach"
    if kind.startswith("career-lab-"):
        return "/career-lab"
    if kind.startswith("mock-interview-"):
        return "/interview"
    if kind.startswith("scout-"):
        return "/scout"
    if kind in {"gmailSync", "mailboxSync"}:
        return "/settings/notifications"
    if kind in {
        "profile-build",
        "profile-skills-rebuild",
        "github-sync",
        "refreshClusters",
        "maintainTaxonomy",
        "undoTaxonomyMaintenance",
    }:
        return "/profile"
    if kind in {
        "pull",
        "discover",
        "refresh",
        "reprocess",
        "addJobUrl",
        "importUrls",
        "linkedinScrape",
    }:
        return "/triage"
    if kind in {
        "tailor",
        "render",
        "revise",
        "redo",
        "coverLetter",
        "coverLetterRevise",
        "companyIntelligence",
        "rolePreparation",
        "hiringContactIntelligence",
        "h1bSponsorship",
        "emailDraft",
    }:
        return "/pipeline"
    return "/"


def completion_results(
    session: Session,
    rows: Sequence[RunCompletion],
    *,
    session_exists: SessionExists | None = None,
) -> list[RunCompletionOut]:
    """Resolve links in a batch without replaying work or altering read state."""
    if not rows:
        return []
    targets = {
        row.run_id: row
        for row in session.exec(
            select(RunCompletionTarget).where(
                col(RunCompletionTarget.run_id).in_([row.run_id for row in rows])
            )
        ).all()
    }
    resume_ids = [
        target.resume_version_id
        for target in targets.values()
        if target.resume_version_id is not None
    ]
    letter_ids = [
        target.cover_letter_id
        for target in targets.values()
        if target.cover_letter_id is not None
    ]
    resumes = (
        {
            artifact_id: (job_id, created_at)
            for artifact_id, job_id, created_at in session.exec(
                select(
                    ResumeVersion.id, ResumeVersion.job_id, ResumeVersion.created_at
                ).where(col(ResumeVersion.id).in_(resume_ids))
            ).all()
        }
        if resume_ids
        else {}
    )
    letters = (
        {
            artifact_id: (job_id, created_at)
            for artifact_id, job_id, created_at in session.exec(
                select(
                    CoverLetter.id, CoverLetter.job_id, CoverLetter.created_at
                ).where(col(CoverLetter.id).in_(letter_ids))
            ).all()
        }
        if letter_ids
        else {}
    )
    job_ids = (
        {job_id for target in targets.values() for job_id in target.job_ids_json}
        | {job_id for job_id, _ in resumes.values()}
        | {job_id for job_id, _ in letters.values()}
    )
    job_created_at = (
        dict(
            session.exec(
                select(Job.id, Job.created_at).where(col(Job.id).in_(job_ids))
            ).all()
        )
        if job_ids
        else {}
    )
    steps = application_next_steps(session, job_ids)
    outputs: list[RunCompletionOut] = []
    for row in rows:
        output = RunCompletionOut.model_validate(row)
        output.result_href = _workspace(row.kind)
        target = targets.get(row.run_id)
        if target is None:
            outputs.append(output)
            continue
        if target.session_id and _workspace(row.kind) in {
            "/coach",
            "/career-lab",
            "/interview",
            "/scout",
        }:
            if session_exists and session_exists(row.kind, target.session_id):
                output.result_href += "?" + urlencode({"session": target.session_id})
                output.result_available = row.status == "succeeded"
            outputs.append(output)
            continue
        ids = list(target.job_ids_json)
        resume = resumes.get(target.resume_version_id)
        letter = letters.get(target.cover_letter_id)
        if resume and not _existed_at(resume[1], row.completed_at):
            resume = None
        if letter and not _existed_at(letter[1], row.completed_at):
            letter = None
        artifact = resume if target.resume_version_id is not None else letter
        if artifact is not None:
            ids = [artifact[0]]
        live_steps = [
            steps[job_id]
            for job_id in ids
            if job_id in steps and _existed_at(job_created_at[job_id], row.completed_at)
        ]
        if live_steps:
            output.result_href = (
                live_steps[0].href if len(live_steps) == 1 else "/pipeline"
            )
            artifact_missing = (
                target.resume_version_id is not None
                and resume is None
                or target.cover_letter_id is not None
                and letter is None
            )
            output.result_available = row.status == "succeeded" and not artifact_missing
            if len(live_steps) == 1 and live_steps[0].kind != "track":
                tab = {
                    "revise": "resumes",
                    "render": "resumes",
                    "coverLetter": "coverLetters",
                    "coverLetterRevise": "coverLetters",
                    "companyIntelligence": "job",
                    "hiringContactIntelligence": "job",
                    "h1bSponsorship": "sponsorship",
                    "rolePreparation": "interview",
                }.get(row.kind)
                if tab:
                    output.result_href = (
                        f"/pipeline?job={live_steps[0].job_id}&tab={tab}"
                    )
        outputs.append(output)
    return outputs
