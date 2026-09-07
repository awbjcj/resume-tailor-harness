"""Public URL analysis, editable drafts and atomic source approval."""

from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.engine import CursorResult
from sqlmodel import Session, col, select

from resume_tailor_harness.config import get_settings
from resume_tailor_harness.db import make_engine
from resume_tailor_harness.discovery.connectors.dates import parse_iso_datetime
from resume_tailor_harness.discovery.merge import IncomingJob
from resume_tailor_harness.discovery.scraper.browser_worker import (
    BrowserUnavailable,
    BrowserWorker,
    snapshot_from_html,
)
from resume_tailor_harness.discovery.scraper.contracts import (
    ApprovalResult,
    CrawlLimits,
    Draft,
    FieldName,
    JsonValue,
    Observation,
    OverridePatch,
    JobFacts,
    NavigationOutcome,
    ValidationResult,
)
from resume_tailor_harness.discovery.scraper.extract import (
    build_extract_agent,
    extract_observation,
)
from resume_tailor_harness.discovery.scraper.identity import (
    board_key,
    normalize_board_url,
)
from resume_tailor_harness.discovery.scraper.pacing import CrawlBudget, HostScheduler
from resume_tailor_harness.discovery.scraper.replay import replay
from resume_tailor_harness.discovery.scraper.store import RevisionConflict, ScrapeStore
from resume_tailor_harness.discovery.scraper.tables import (
    ScrapeApprovalRow,
    ScrapeObservationRow,
    ScrapeOverrideRow,
    ScrapeSourceRow,
    ScrapeRevisionRow,
)
from resume_tailor_harness.discovery.scraper.understand import (
    build_understand_agent,
    understand,
)
from resume_tailor_harness.discovery.scraper.validate import validate_plan
from resume_tailor_harness.security.browser_gateway import (
    BrowserGateway,
)
from resume_tailor_harness.security.outbound import validate_public_url
from resume_tailor_harness.services.scrape_ingest import (
    ingest_observation,
    find_observed_job,
)
from resume_tailor_harness.tenancy.context import current_context
from resume_tailor_harness.tracking.repository import (
    company_rename_collides,
    has_progress,
)
from resume_tailor_harness.tracking.tables import Job, JobStatus


def build_gateway() -> BrowserGateway:
    context = current_context()
    engine = context.system_engine if context else None
    if engine is None:
        engine = make_engine(
            f"sqlite:///{(Path('data') / 'crawl-system.db').absolute().as_posix()}"
        )
    return BrowserGateway(HostScheduler(engine))


def analyze_url(
    session: Session,
    url: str,
    limits: CrawlLimits,
    *,
    checkpoint=None,
    allow_browser: bool = True,
) -> Draft:
    from resume_tailor_harness.tenancy.limits import enforce_active_budget

    enforce_active_budget()
    url = normalize_board_url(url)
    validate_public_url(url)
    store = ScrapeStore(session)
    draft = Draft(source_id=board_key(url), url=url, limits=limits)
    source = session.get(ScrapeSourceRow, draft.source_id)
    draft.base_revision = source.revision if source else 0
    budget = _budget(limits, checkpoint)
    gateway = build_gateway()
    response = gateway.document(url, budget)
    if response.status != 200:
        raise ValueError(f"Website returned HTTP {response.status}")
    listing = snapshot_from_html(
        response.final_url, response.body.decode("utf-8", errors="replace"), url
    )
    learner = build_understand_agent()
    extractor = build_extract_agent()
    understanding = understand(listing, learner)
    static_sample = (
        extract_observation(listing, draft.source_id, 0, extractor)
        if understanding.kind == "posting"
        else None
    )
    with BrowserWorker(gateway) as worker:
        needs_browser = (
            understanding.kind not in {"posting", "listing", "blocked"}
            or (understanding.kind == "listing" and understanding.plan is None)
            or (understanding.kind == "posting" and not static_sample.accepted)
        )
        if needs_browser:
            if not allow_browser or not get_settings().public_browser_enabled:
                raise BrowserUnavailable(
                    "Browser extraction is unavailable on this installation"
                )
            listing = worker.snapshot(url, budget)
            understanding = understand(listing, learner)
            static_sample = None
        store.save_snapshot(listing)
        draft.page_kind = understanding.kind
        if understanding.kind in {"empty_listing", "blocked", "unrelated"}:
            draft.state = "unverified"
            draft.navigation = NavigationOutcome(
                terminal_reason=(
                    "empty"
                    if understanding.kind == "empty_listing"
                    else "blocked"
                    if understanding.kind == "blocked"
                    else "review_required"
                )
            )
        elif understanding.kind == "posting":
            sample = static_sample or extract_observation(
                listing, draft.source_id, 0, extractor
            )
            store.save_observation(sample)
            draft.samples = [sample]
            draft.plan = understanding.plan
            draft.validation = ValidationResult(
                valid=sample.accepted and draft.plan is not None
            )
            draft.navigation = NavigationOutcome(
                terminal_reason="complete" if sample.accepted else "review_required",
                discovered=1,
                inspected=1,
                messages=[issue.message for issue in sample.issues if issue.message],
            )
        elif understanding.plan:
            if not allow_browser or not get_settings().public_browser_enabled:
                raise BrowserUnavailable(
                    "Browser extraction is unavailable on this installation"
                )
            draft.plan = understanding.plan
            report = replay(
                draft, worker, store, extractor, preview=True, budget=budget
            )
            draft.samples = report.observations
            draft.navigation = _navigation_outcome(report)
            detail_ids = {
                item.snapshot_id for sample in draft.samples for item in sample.evidence
            }
            details = [store.get_snapshot(key) for key in detail_ids]
            if details and not draft.plan.detail_selector:
                refined = understand(listing, learner, details)
                draft.plan = refined.plan or draft.plan
            draft.validation = validate_plan(draft.plan, listing, details)
            draft.validation.valid = (
                draft.validation.valid
                and bool(draft.samples)
                and all(sample.accepted for sample in draft.samples)
                and not report.failed
                and report.terminal_reason in {"complete", "partial_limit"}
            )
    if draft.validation.valid:
        draft.state = "validated"
    capture_override_revisions(session, draft)
    saved = store.save_draft(draft)
    session.commit()
    return saved


def revalidate_draft(
    session: Session, draft_id: str, expected_revision: int, *, checkpoint=None
) -> Draft:
    store = ScrapeStore(session)
    draft = store.get_draft(draft_id)
    if draft.revision != expected_revision:
        raise RevisionConflict("draft changed")
    if draft.plan is None:
        raise ValueError("Select extraction rules first")
    with BrowserWorker(build_gateway()) as worker:
        report = replay(
            draft,
            worker,
            store,
            build_extract_agent(),
            preview=True,
            budget=_budget(draft.limits, checkpoint),
        )
    draft.samples = report.observations
    draft.navigation = _navigation_outcome(report)
    apply_corrections(draft)
    draft.validation = ValidationResult(
        valid=bool(draft.samples)
        and all(item.accepted for item in draft.samples)
        and not report.failed
        and (
            report.terminal_reason in {"complete", "partial_limit"}
            or (report.terminal_reason == "review_required" and not report.messages)
        )
    )
    draft.state = "validated" if draft.validation.valid else "draft"
    draft = store.save_draft(draft)
    session.commit()
    return draft


def approve_draft(
    session: Session, draft_id: str, expected_revision: int, selected_keys: list[str]
) -> ApprovalResult:
    store = ScrapeStore(session)
    try:
        receipt = session.get(ScrapeApprovalRow, draft_id)
        if receipt:
            store.approve(draft_id, expected_revision)
            return ApprovalResult.model_validate_json(receipt.payload)
        draft = store.get_draft(draft_id)
        samples = {item.job_key: item for item in draft.samples if item.job_key}
        if not set(selected_keys).issubset(samples):
            raise ValueError("Selected sample was not observed")
        approved = store.approve(draft_id, expected_revision)
        job_ids = []
        inline_listing = (
            draft.page_kind == "listing"
            and draft.plan is not None
            and draft.plan.detail_mode != "link"
        )
        for key in dict.fromkeys(selected_keys):
            sample = samples[key]
            if (
                not sample.accepted
                or not sample.facts.title
                or not sample.facts.jd_text
            ):
                raise ValueError("Correct invalid sample fields before approval")
            for field, value in draft.corrections.get(key, {}).items():
                store.set_override(
                    key,
                    OverridePatch(
                        field=cast(FieldName, field),
                        value=cast(JsonValue, value),
                        expected_revision=draft.correction_revisions.get(key, {}).get(
                            field, 0
                        ),
                    ),
                )
            job_id = ingest_observation(
                session,
                sample,
                store,
                inline=inline_listing,
            )
            if job_id is not None:
                job_ids.append(job_id)
        result = ApprovalResult(
            source_id=draft.source_id,
            approved_revision=approved.revision,
            job_ids=job_ids,
        )
        session.add(
            ScrapeApprovalRow(draft_id=draft_id, payload=result.model_dump_json())
        )
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


def set_job_override(
    session: Session, job_id: int, field: FieldName, patch: OverridePatch
) -> int:
    """Save a correction and immediately project its effective facts onto its job."""
    if patch.field != field:
        raise ValueError("Field does not match request path")
    try:
        row, job_key = _latest_job_observation(session, job_id)
        store = ScrapeStore(session)
        revision = store.set_override(job_key, patch)
        _sync_job_source_facts(session, job_id, row, store, field)
        session.commit()
        return revision
    except Exception:
        session.rollback()
        raise


def clear_job_override(
    session: Session, job_id: int, field: FieldName, expected_revision: int
) -> int:
    """Remove a correction and restore the source value on its canonical job."""
    try:
        row, job_key = _latest_job_observation(session, job_id)
        store = ScrapeStore(session)
        revision = store.remove_override(job_key, field, expected_revision)
        _sync_job_source_facts(session, job_id, row, store, field)
        session.commit()
        return revision
    except Exception:
        session.rollback()
        raise


def _latest_job_observation(
    session: Session, job_id: int
) -> tuple[ScrapeObservationRow, str]:
    row = session.exec(
        select(ScrapeObservationRow)
        .where(ScrapeObservationRow.job_id == job_id)
        .order_by(col(ScrapeObservationRow.observed_at).desc())
    ).first()
    if row is None or row.job_key is None:
        raise KeyError(job_id)
    return row, row.job_key


def _sync_job_source_facts(
    session: Session,
    job_id: int,
    row: ScrapeObservationRow,
    store: ScrapeStore,
    field: FieldName,
) -> None:
    """Apply one observation's effective facts without discarding user artifacts."""
    job = session.get(Job, job_id)
    if job is None:
        raise KeyError(job_id)
    observation = Observation.model_validate_json(row.payload)
    facts = store.effective_facts(observation)
    progressed = job.id is not None and has_progress(session, job.id)
    incoming = IncomingJob.clean(
        source=job.source,
        url=job.url,
        company=facts.company if field == "company" else job.company,
        title=facts.title if field == "title" else job.title,
        location=(
            "; ".join(facts.locations) if facts.locations else None
        )
        if field == "locations"
        else job.location,
        jd_text=(facts.jd_text or "") if field == "jd_text" else job.jd_text,
        posted_at=(
            parse_iso_datetime(facts.posted_at)
            if field == "posted_at"
            else job.posted_at
        ),
    )
    if (
        incoming.dedup_key != job.dedup_key
        and company_rename_collides(
            session, existing=job, dedup_key=incoming.dedup_key
        )
    ):
        raise ValueError("Corrected title and company conflict with another active job")

    if field in {"company", "title", "locations", "jd_text", "posted_at"}:
        job.company = incoming.company
        job.title = incoming.title
        job.location = incoming.location
        job.jd_text = incoming.jd_text
        job.posted_at = incoming.posted_at
        job.dedup_key = incoming.dedup_key
        job.content_fingerprint = incoming.content_fingerprint
    if field in {
        "title",
        "company",
        "jd_text",
        "locations",
        "salary_bands",
        "remote_policy",
        "remote_restrictions",
        "attendance",
        "employment_type",
    }:
        job.criteria_json = None
        job.analysis_meta_json = None
        job.fit_score = None
        job.fit_rationale = None
        job.reject_reason = None
        job.reject_category = None
        job.industry_pending = False
    if not progressed:
        job.status = JobStatus.raw.value
    # This explicit correction promotes the selected observation even when an
    # earlier automatic ingest left it unapplied to protect user progress.
    if not progressed:
        row.applied = True
    session.add(row)
    session.add(job)
    session.flush()


def pull_source(
    session: Session,
    source_id: str,
    *,
    refresh: bool = False,
    checkpoint=None,
    search=None,
):
    from resume_tailor_harness.services.discovery import ActiveJobQuotaError

    row = session.get(ScrapeSourceRow, source_id)
    if row is None:
        raise KeyError(source_id)
    draft = Draft.model_validate_json(row.payload)
    if not row.enabled or draft.state != "approved":
        raise ValueError("Validate and approve this source before pulling")
    store = ScrapeStore(session)
    budget = _budget(draft.limits, checkpoint)
    inline_listing = (
        draft.page_kind == "listing"
        and draft.plan is not None
        and draft.plan.detail_mode != "link"
    )
    with BrowserWorker(build_gateway()) as worker:
        report = replay(
            draft,
            worker,
            store,
            build_extract_agent(),
            refresh=refresh,
            budget=budget,
        )
    for observation in report.observations:
        if search is not None:
            from resume_tailor_harness.discovery.connectors.base import RawJob
            from resume_tailor_harness.discovery.connectors.text import relevance_gate

            facts = store.effective_facts(observation)
            raw = RawJob(
                source="scrape",
                title=facts.title,
                company=facts.company,
                url=facts.source_url,
                location="; ".join(facts.locations) if facts.locations else None,
                jd_text=facts.jd_text or "",
            )
            if not relevance_gate([raw], search):
                report.filtered += 1
                continue
        existing = find_observed_job(
            session,
            observation,
            store,
            inline=inline_listing,
        )
        try:
            job_id = ingest_observation(
                session,
                observation,
                store,
                inline=inline_listing,
            )
        except ActiveJobQuotaError as exc:
            # A quota only blocks this new canonical row. Keep observations and
            # jobs already flushed in this pull rather than rolling back the
            # complete source transaction.
            if report.terminal_reason == "complete":
                report.terminal_reason = "partial_limit"
            if str(exc) not in report.messages:
                report.messages.append(str(exc))
            continue
        if job_id is not None:
            if existing is None:
                report.imported += 1
            else:
                report.duplicate += 1
    if report.terminal_reason == "review_required" and budget.clock() < budget.deadline:
        listing = store.cached_snapshot(f"{draft.source_id}:listing")
        if listing is not None:
            try:
                budget.check_deadline()
                ids = list(
                    dict.fromkeys(
                        item.snapshot_id
                        for observation in report.observations
                        for item in observation.evidence
                    )
                )[:3]
                details = [store.get_snapshot(key) for key in ids]
                learned = understand(listing, build_understand_agent(), details)
                if learned.plan is not None:
                    proposal = draft.model_copy(
                        update={
                            "id": uuid4().hex,
                            "revision": 0,
                            "base_revision": row.revision,
                            "plan": learned.plan,
                            "state": "draft",
                            "validation": ValidationResult(),
                            "samples": report.observations,
                            "corrections": {},
                        }
                    )
                    capture_override_revisions(session, proposal)
                    store.save_draft(proposal)
                    report.repair_draft_id = proposal.id
            except Exception as exc:
                report.messages.append(f"Rule repair requires another review: {exc}")
    session.commit()
    return report


def import_public_url(
    session: Session,
    url: str,
    *,
    company: str | None = None,
    title: str | None = None,
    location: str | None = None,
    checkpoint=None,
    allow_browser: bool = True,
):
    draft = analyze_url(
        session, url, CrawlLimits(), checkpoint=checkpoint, allow_browser=allow_browser
    )
    if (
        draft.page_kind != "posting"
        or len(draft.samples) != 1
        or not draft.samples[0].accepted
    ):
        return {"jobId": None, "duplicate": False, "draftId": draft.id}
    sample = draft.samples[0]
    store = ScrapeStore(session)
    for raw_field, value in (
        ("company", company),
        ("title", title),
        ("locations", [location] if location else None),
    ):
        if value is not None and sample.job_key:
            field = cast(FieldName, raw_field)
            existing = session.get(ScrapeOverrideRow, (sample.job_key, field))
            store.set_override(
                sample.job_key,
                OverridePatch(
                    field=field,
                    value=cast(JsonValue, value),
                    expected_revision=existing.revision if existing else 0,
                ),
            )
    existing_job = find_observed_job(session, sample, store)
    job_id = ingest_observation(session, sample, store)
    session.commit()
    return {"jobId": job_id, "duplicate": existing_job is not None}


def edit_source(session: Session, source_id: str) -> Draft:
    row = session.get(ScrapeSourceRow, source_id)
    if row is None:
        raise KeyError(source_id)
    draft = Draft.model_validate_json(row.payload).model_copy(
        update={
            "id": uuid4().hex,
            "revision": 0,
            "base_revision": row.revision,
            "state": "draft",
            "validation": ValidationResult(),
            "corrections": {},
        }
    )
    capture_override_revisions(session, draft)
    draft = ScrapeStore(session).save_draft(draft)
    session.commit()
    return draft


def _budget(limits: CrawlLimits, checkpoint=None) -> CrawlBudget:
    def cancelled():
        if checkpoint is not None:
            checkpoint()
        return False

    return CrawlBudget(limits, cancelled=cancelled)


def _navigation_outcome(report) -> NavigationOutcome:
    return NavigationOutcome(
        terminal_reason=report.terminal_reason,
        discovered=report.discovered,
        inspected=report.inspected,
        messages=report.messages,
    )


def patch_draft(
    session: Session,
    draft_id: str,
    expected_revision: int,
    *,
    plan=None,
    limits=None,
    samples=None,
) -> Draft:
    store = ScrapeStore(session)
    draft = store.get_draft(draft_id)
    if draft.revision != expected_revision:
        raise RevisionConflict("draft changed; reload before editing")
    if plan is not None:
        draft.plan = plan
        draft.validation = ValidationResult()
        draft.state = "draft"
    if limits is not None:
        draft.limits = limits
    if samples:
        keys = {sample.job_key for sample in draft.samples}
        if not set(samples).issubset(keys):
            raise ValueError("Only observed samples can be corrected")
        for sample in draft.samples:
            if sample.job_key is not None and sample.job_key in samples:
                corrected = samples[sample.job_key]
                for field, value in corrected.model_dump(mode="json").items():
                    if field in {"source_url", "posting_id"}:
                        if value != getattr(sample.facts, field):
                            raise ValueError("Posting identity cannot be edited")
                        continue
                    if value != sample.facts.model_dump(mode="json")[field]:
                        draft.corrections.setdefault(sample.job_key, {})[
                            cast(FieldName, field)
                        ] = cast(JsonValue, value)
                sample.facts = corrected
    apply_corrections(draft)
    if (
        plan is None
        and draft.state == "validated"
        and draft.plan
        and not draft.validation.issues
        and draft.samples
        and all(item.accepted for item in draft.samples)
    ):
        draft.validation.valid = True
        draft.state = "validated"
    draft = store.save_draft(draft)
    session.commit()
    return draft


def apply_corrections(draft: Draft) -> None:
    for sample in draft.samples:
        if sample.job_key is None:
            continue
        corrections = draft.corrections.get(sample.job_key, {})
        if not corrections:
            continue
        sample.facts = JobFacts.model_validate(
            {**sample.facts.model_dump(), **corrections}
        )
        sample.issues = [
            issue for issue in sample.issues if issue.field not in corrections
        ]
        sample.accepted = bool(
            sample.job_key and sample.facts.title and sample.facts.jd_text
        ) and not any(issue.kind != "not_stated" for issue in sample.issues)


def snapshot_elements(session: Session, snapshot_id: str) -> list[dict[str, str]]:
    from bs4 import BeautifulSoup

    snapshot = ScrapeStore(session).get_snapshot(snapshot_id)
    soup = BeautifulSoup(snapshot.html, "html.parser")
    result = []
    for node in soup.select("h1,h2,h3,p,article,section,div,span,a,time,li"):
        text = node.get_text(" ", strip=True)
        if not text or node.find_parent(["script", "style", "noscript"]):
            continue
        parts = []
        current = node
        while current and current.name != "[document]":
            siblings = current.find_previous_siblings(current.name)
            parts.append(f"{current.name}:nth-of-type({len(siblings) + 1})")
            current = current.parent
        selector = " > ".join(reversed(parts))
        if len(selector) <= 500:
            result.append({"selector": selector, "text": text[:400]})
        if len(result) >= 300:
            break
    return result


def list_sources(session: Session) -> list[Draft]:
    from resume_tailor_harness.discovery.connectors.config import load_connectors_config
    from resume_tailor_harness.tenancy.paths import CONNECTORS_PATH, resolve_tenant_path
    from resume_tailor_harness.discovery.scraper.recipe_store import (
        load_recipe,
        host_key,
        default_recipes_dir,
    )
    from resume_tailor_harness.discovery.scraper.contracts import BoardPlan, FieldRule

    path = resolve_tenant_path(CONNECTORS_PATH)
    if path.exists():
        for target in load_connectors_config(path).scrape.targets:
            key = board_key(target.url)
            if session.get(ScrapeSourceRow, key) is not None:
                continue
            recipe = load_recipe(host_key(target.url), default_recipes_dir())
            plan = None
            if recipe:
                plan = BoardPlan(
                    card_selector=recipe.card_container,
                    detail_selector=recipe.jd_container,
                    link_selector=recipe.url_sel,
                    detail_mode=recipe.detail_mode,
                    pagination=recipe.pagination.pattern,
                    control_selector=recipe.pagination.control_sel,
                    field_rules=[FieldRule(field="title", selector=recipe.title_sel)],
                )
            draft = Draft(
                source_id=key,
                url=normalize_board_url(target.url),
                plan=plan,
                state="unverified",
            )
            session.add(
                ScrapeSourceRow(
                    id=key,
                    url=draft.url,
                    revision=0,
                    enabled=False,
                    payload=draft.model_dump_json(),
                )
            )
        session.commit()
    return [
        Draft.model_validate_json(row.payload).model_copy(
            update={"enabled": row.enabled}
        )
        for row in ScrapeStore(session).list_sources()
    ]


def set_source_enabled(
    session: Session, source_id: str, expected_revision: int, enabled: bool
) -> Draft:
    from sqlalchemy import update

    row = session.get(ScrapeSourceRow, source_id)
    if row is None:
        raise KeyError(source_id)
    draft = Draft.model_validate_json(row.payload)
    if enabled and draft.state != "approved":
        raise ValueError("Approve this source before enabling it")
    result = session.execute(
        update(ScrapeSourceRow)
        .where(
            col(ScrapeSourceRow.id) == source_id,
            col(ScrapeSourceRow.revision) == expected_revision,
        )
        .values(enabled=enabled)
    )
    if cast(CursorResult[Any], result).rowcount != 1:
        raise RevisionConflict("source revision changed")
    session.commit()
    return draft.model_copy(update={"enabled": enabled})


def capture_override_revisions(session: Session, draft: Draft) -> None:
    from sqlmodel import select

    keys = [item.job_key for item in draft.samples if item.job_key]
    draft.correction_revisions = {}
    for row in session.exec(
        select(ScrapeOverrideRow).where(col(ScrapeOverrideRow.job_key).in_(keys))
    ).all():
        draft.correction_revisions.setdefault(row.job_key, {})[
            cast(FieldName, row.field)
        ] = row.revision


def rollback_source(
    session: Session, source_id: str, revision_number: int, expected_revision: int
) -> Draft:
    source = session.get(ScrapeSourceRow, source_id)
    revision = session.get(ScrapeRevisionRow, (source_id, revision_number))
    if source is None or revision is None:
        raise KeyError(source_id)
    if source.revision != expected_revision:
        raise RevisionConflict("source revision changed")
    draft = Draft.model_validate_json(revision.payload).model_copy(
        update={
            "id": uuid4().hex,
            "revision": 0,
            "base_revision": source.revision,
            "state": "validated",
        }
    )
    store = ScrapeStore(session)
    store.save_draft(draft)
    approved = store.approve(draft.id, 0)
    session.commit()
    return approved
