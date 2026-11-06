"""Redo any pipeline stage on explicitly chosen jobs.

The automatic paths (pull/discover/refresh/reprocess) guard against clobbering
user work. Redo runs the selected stages explicitly and keeps the job's status
as a high-water mark. It appends resume attempts and can clean up superseded
versions after a successful replacement.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

import httpx
from playwright.sync_api import Error as PlaywrightError
from sqlmodel import Session

from resume_tailor_harness.config import get_settings
from resume_tailor_harness.discovery.pipeline import (
    StageScope,
    run_extract,
    run_filter,
    run_score,
)
from resume_tailor_harness.discovery.search_config import load_search_config
from resume_tailor_harness.discovery.url_ingest.service import job_from_url
from resume_tailor_harness.discovery.url_ingest.recovery import (
    RecoveryHints,
    RecoveryRequired,
)
from resume_tailor_harness.profile.store import load_facts
from resume_tailor_harness.progress import ProgressReporter, RunCancelled
from resume_tailor_harness.services.agents import (
    build_discovery_bundle,
    build_url_extract_agent,
)
from resume_tailor_harness.services.discovery import _skill_artifacts
from resume_tailor_harness.services.errors import (
    StageFailure,
    record_job_failure,
    resolve_job_failures,
)
from resume_tailor_harness.services.redo_versions import (
    VersionRef,
    remove_superseded_versions,
    snapshot_previous_versions,
)
from resume_tailor_harness.services.rendering import render_resume_version
from resume_tailor_harness.services.tailoring import tailor
from resume_tailor_harness.taxonomy.location import join_locations
from resume_tailor_harness.tenancy.limits import enforce_active_budget
from resume_tailor_harness.tenancy.paths import FACTS_PATH, SEARCH_PATH
from resume_tailor_harness.tracking.dedup import (
    compute_content_fingerprint,
    compute_dedup_key,
)
from resume_tailor_harness.tracking.repository import (
    application_for_job,
    company_rename_collides,
    get_job,
    latest_resume_version_id,
    save_job,
)
from resume_tailor_harness.tracking.tables import Job, ResumeVersion

logger = logging.getLogger(__name__)

RedoStage = Literal["pull", "extract", "tailor", "render"]

# Stages always run in pipeline order, whatever order the caller listed them.
REDO_STAGES: tuple[RedoStage, ...] = ("pull", "extract", "tailor", "render")


@dataclass(frozen=True)
class StageOutcome:
    """One job's result for one stage, as reported in the run payload.

    Distinct from StageFailure, which is the durable diagnostic written to
    ErrorRecord. `detail` carries the same one-line message.
    """

    job_id: int
    stage: RedoStage
    status: Literal["ok", "skipped", "failed"]
    detail: str | None = None
    version: VersionRef | None = None
    removed_version_ids: tuple[int, ...] = ()
    cleanup_error: str | None = None


def repull_job(
    session: Session,
    job: Job,
    *,
    agent,
    allow_browser: bool,
) -> tuple[StageOutcome, StageFailure | None]:
    """Re-fetch a job's posting and replace its description in place.

    Deliberately bypasses find_existing/decide/_apply. That machinery answers
    "is this the same job, and does it outrank what I hold?" -- already settled
    for a row the user picked -- and it is what freezes jd_text at merge.py:179.
    """
    job_id = job.id
    if job_id is None:
        raise ValueError("cannot re-pull an unsaved job")
    if not job.url:
        return StageOutcome(job_id, "pull", "skipped", "no source URL"), None

    try:
        raw = job_from_url(
            job.url,
            agent=agent,
            allow_browser=allow_browser,
            **(
                {"recovery_hints": RecoveryHints(job.company, job.title, job.location)}
                if job.company and job.title
                else {}
            ),
        )
    except (httpx.HTTPError, PlaywrightError, RecoveryRequired) as exc:
        logger.warning("repull job=%s failed", job_id, exc_info=exc)
        failure = StageFailure.from_exception(exc)
        # Run outcomes retain candidate links even when the compact error-card
        # summary is truncated to 300 characters.
        detail = f"{failure.error_type}: {exc if isinstance(exc, RecoveryRequired) else failure.message}"
        return StageOutcome(job_id, "pull", "failed", detail), failure

    if raw is None or not raw.jd_text.strip():
        detail = "no job description found"
        return (
            StageOutcome(job_id, "pull", "failed", detail),
            StageFailure(error_type="UrlFetchError", message=detail, traceback_tail=""),
        )

    detail = None
    job.jd_text = raw.jd_text
    if raw.url and raw.url != job.url:
        detail = f"Recovered employer posting: {job.url} -> {raw.url}"
        job.url = raw.url
    job.content_fingerprint = compute_content_fingerprint(raw.jd_text)
    if raw.location:
        job.location = join_locations([raw.location])

    company = raw.company or job.company
    title = raw.title or job.title
    if company != job.company or title != job.title:
        new_key = compute_dedup_key(company, title)
        if company_rename_collides(session, existing=job, dedup_key=new_key):
            # Another live row already holds that identity. Take the text and
            # leave company/title/dedup_key alone rather than stealing it.
            logger.info("repull job=%s kept identity (key collision)", job_id)
        else:
            job.company = company
            job.title = title
            job.dedup_key = new_key

    save_job(session, job)
    return StageOutcome(job_id, "pull", "ok", detail), None


def _settle(
    session: Session,
    job: Job,
    outcome: StageOutcome,
    failure: StageFailure | None,
    run_id: str | None,
    model: str | None = None,
) -> StageOutcome:
    try:
        if failure is not None:
            record_job_failure(
                session,
                job=job,
                stage=outcome.stage,
                failure=failure,
                run_id=run_id,
                model=model,
            )
        elif outcome.status == "ok":
            resolve_job_failures(session, outcome.job_id, outcome.stage)
    except Exception:
        session.rollback()
        logger.warning(
            "could not update failure records for job=%s stage=%s",
            outcome.job_id,
            outcome.stage,
            exc_info=True,
        )
    return outcome


def _stage_result(
    session: Session,
    job: Job,
    stage: RedoStage,
    failure: StageFailure | None,
    run_id: str | None,
    *,
    model: str | None = None,
    version: VersionRef | None = None,
) -> StageOutcome:
    assert job.id is not None
    outcome = (
        StageOutcome(
            job.id, stage, "failed", f"{failure.error_type}: {failure.message}"
        )
        if failure is not None
        else StageOutcome(job.id, stage, "ok", version=version)
    )
    return _settle(session, job, outcome, failure, run_id, model)


def _run_pull(
    session: Session,
    jobs: list[Job],
    run_id: str | None,
    reporter: ProgressReporter | None,
) -> list[StageOutcome]:
    agent = build_url_extract_agent()
    allow_browser = get_settings().browser_enabled
    outcomes = []
    for job in jobs:
        if reporter is not None:
            reporter.checkpoint()
        outcome, failure = repull_job(
            session, job, agent=agent, allow_browser=allow_browser
        )
        outcomes.append(_settle(session, job, outcome, failure, run_id))
    return outcomes


def _run_extract(
    session: Session,
    jobs: list[Job],
    run_id: str | None,
    reporter: ProgressReporter | None,
) -> list[StageOutcome]:
    """Re-run extract -> filter -> score over these ids, forward-only.

    run_relevance is deliberately not run: it exists to reject off-target raw
    rows, so under never_regress it is a guaranteed no-op.
    """
    config = load_search_config(SEARCH_PATH)
    facts = load_facts(FACTS_PATH)
    matrix, cluster_map = _skill_artifacts(FACTS_PATH, facts)
    bundle = build_discovery_bundle()
    ids = frozenset(job.id for job in jobs if job.id is not None)
    failures = run_extract(
        session,
        bundle.extract,
        scope=StageScope(job_ids=ids, any_status=True, never_regress=True),
        industry_classifier=bundle.industry_classifier,
    )
    score_ids = ids.difference(failures)
    if score_ids:
        if reporter is not None:
            reporter.checkpoint()
        scope = StageScope(job_ids=score_ids, any_status=True, never_regress=True)
        run_filter(session, config, scope)
        failures.update(
            run_score(
                session,
                facts,
                bundle.fit,
                canonicalizer=bundle.canonicalizer,
                scope=scope,
                matrix=matrix,
                cluster_map=cluster_map,
            )
        )
    return [
        _stage_result(
            session,
            job,
            "extract",
            failures.get(job.id) if job.id is not None else None,
            run_id,
        )
        for job in jobs
    ]


def _run_tailor(
    session: Session,
    jobs: list[Job],
    run_id: str | None,
    deep: bool,
) -> list[StageOutcome]:
    from resume_tailor_harness.services.tailoring import (
        DEFAULT_REVIEW,
        DEFAULT_REVIEW_DEEP,
    )

    ids = [job.id for job in jobs if job.id is not None]
    outcome = tailor(
        session,
        job_ids=ids,
        review_path=DEFAULT_REVIEW_DEEP if deep else DEFAULT_REVIEW,
    )
    results = []
    for job in jobs:
        assert job.id is not None
        failure = outcome.failures.get(job.id)
        versions = outcome.versions.get(job.id)
        if failure is None and not versions:
            failure = StageFailure(
                "MissingResumeVersion", "tailoring produced no resume version", ""
            )
        results.append(
            _stage_result(
                session,
                job,
                "tailor",
                failure,
                run_id,
                model=outcome.model,
                version=VersionRef.from_row(versions[-1]) if versions else None,
            )
        )
    return results


def _render_target(session: Session, job_id: int) -> int | None:
    """The Application's chosen version, else the highest-id version."""
    application = application_for_job(session, job_id)
    if application is not None and application.resume_version_id is not None:
        return application.resume_version_id
    return latest_resume_version_id(session, job_id)


def _render_job(
    session: Session,
    job: Job,
    run_id: str | None,
    target: VersionRef | None,
) -> StageOutcome:
    assert job.id is not None
    version_id = target.id if target is not None else _render_target(session, job.id)
    if version_id is None:
        return StageOutcome(job.id, "render", "skipped", "no resume version")
    version = session.get(ResumeVersion, version_id, populate_existing=True)
    if (
        version is None
        or version.job_id != job.id
        or (target is not None and VersionRef.from_row(version) != target)
    ):
        return StageOutcome(job.id, "render", "skipped", "resume version unavailable")
    ref = VersionRef.from_row(version)
    try:
        path = render_resume_version(session, version_id)
    except Exception as exc:
        session.rollback()
        logger.warning("render job=%s failed", job.id, exc_info=exc)
        return _stage_result(
            session, job, "render", StageFailure.from_exception(exc), run_id
        )
    if path is None:
        return StageOutcome(job.id, "render", "skipped", "resume version unavailable")
    return _stage_result(session, job, "render", None, run_id, version=ref)


def _run_render(
    session: Session,
    jobs: list[Job],
    run_id: str | None,
    reporter: ProgressReporter | None,
    tailored: dict[int, VersionRef] | None,
) -> list[StageOutcome]:
    outcomes = []
    for job in jobs:
        assert job.id is not None
        if reporter is not None:
            reporter.checkpoint()
        if tailored is not None and job.id not in tailored:
            outcomes.append(
                StageOutcome(job.id, "render", "skipped", "no new resume version")
            )
        else:
            target = tailored[job.id] if tailored is not None else None
            outcomes.append(_render_job(session, job, run_id, target))
    return outcomes


def _cleanup_previous_versions(
    session: Session,
    outcome: StageOutcome,
    previous: set[VersionRef],
    reporter: ProgressReporter | None,
) -> StageOutcome:
    if outcome.status != "ok" or outcome.version is None or not previous:
        return outcome
    try:
        cleanup = remove_superseded_versions(
            session,
            outcome.job_id,
            previous,
            outcome.version,
            checkpoint=reporter.checkpoint if reporter is not None else None,
        )
    except RunCancelled:
        raise
    except Exception as exc:
        session.rollback()
        logger.warning("redo cleanup job=%s failed", outcome.job_id, exc_info=exc)
        return replace(outcome, cleanup_error=StageFailure.from_exception(exc).message)
    return replace(
        outcome, removed_version_ids=cleanup.removed_ids, cleanup_error=cleanup.error
    )


def redo_jobs(
    session: Session,
    *,
    job_ids: Sequence[int],
    stages: Sequence[RedoStage],
    deep: bool = False,
    remove_previous_versions: bool = False,
    previous_versions: Mapping[int, set[VersionRef]] | None = None,
    reporter: ProgressReporter | None = None,
    on_cleanup: Callable[[Sequence[StageOutcome]], None] | None = None,
    run_id: str | None = None,
) -> list[StageOutcome]:
    """Re-run the chosen stages over the chosen jobs, stage-major.

    Inputs are validated at the API boundary (RedoParams): non-empty and
    deduped. This function trusts them.
    """
    enforce_active_budget()
    requested = set(stages)
    ordered: list[RedoStage] = [stage for stage in REDO_STAGES if stage in requested]
    jobs: dict[int, Job] = {}
    outcomes: list[StageOutcome] = []
    for job_id in dict.fromkeys(job_ids):
        job = get_job(session, job_id)
        if job is None:
            outcomes.append(
                StageOutcome(job_id, ordered[0], "skipped", "job not found")
            )
        else:
            jobs[job_id] = job
    if not jobs:
        return outcomes

    previous: Mapping[int, set[VersionRef]] = {}
    if remove_previous_versions and "tailor" in requested:
        previous = (
            previous_versions
            if previous_versions is not None
            else snapshot_previous_versions(session, list(jobs))
        )
    blocked: dict[int, RedoStage] = {}
    tailored: dict[int, VersionRef] | None = None
    runners = {
        "pull": lambda targets: _run_pull(session, targets, run_id, reporter),
        "extract": lambda targets: _run_extract(session, targets, run_id, reporter),
        "tailor": lambda targets: _run_tailor(session, targets, run_id, deep),
        "render": lambda targets: _run_render(
            session, targets, run_id, reporter, tailored
        ),
    }
    for index, stage in enumerate(ordered):
        if reporter:
            reporter.begin(
                len(jobs),
                f"Redo: {stage}",
                phase_index=index + 1,
                phase_count=len(ordered),
            )
        targets = [job for job_id, job in jobs.items() if job_id not in blocked]
        results = runners[stage](targets) if targets else []
        by_job = {result.job_id: result for result in results}
        if stage == "tailor":
            tailored = {
                result.job_id: result.version
                for result in results
                if result.status == "ok" and result.version is not None
            }
        for job_id in jobs:
            if job_id in blocked:
                outcomes.append(
                    StageOutcome(job_id, stage, "skipped", f"{blocked[job_id]} failed")
                )
                continue
            result = by_job.get(job_id)
            if result is None:
                continue
            if result.status == "failed":
                blocked[job_id] = stage
            if stage == ordered[-1] and job_id in previous:
                if reporter is not None:
                    reporter.checkpoint()
                result = _cleanup_previous_versions(
                    session, result, previous[job_id], reporter
                )
            outcomes.append(result)
            if result.removed_version_ids and on_cleanup is not None:
                on_cleanup(outcomes)
        if reporter:
            reporter.step(len(jobs))
    return outcomes
