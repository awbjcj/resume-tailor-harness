"""Workspace-owned public-page review; slow actions use the Run substrate."""

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from resume_tailor_harness.api.deps import get_engine, get_run_manager, get_session
from resume_tailor_harness.api.errors import ApiException
from resume_tailor_harness.api.runs.launch import launch, session_work
from resume_tailor_harness.api.schemas.runs import RunOut
from resume_tailor_harness.api.schemas.scrape import (
    AnalyzeIn,
    ApprovalResultOut,
    ApproveIn,
    DraftOut,
    DraftPatchIn,
    RevisionIn,
    RollbackIn,
    OverrideOut,
    OverridePatchIn,
    OverrideRevisionOut,
    ObservationOut,
    SnapshotElement,
    SourceStateIn,
)
from resume_tailor_harness.discovery.scraper.contracts import FieldName, OverridePatch
from resume_tailor_harness.discovery.scraper.store import RevisionConflict
from resume_tailor_harness.services import (
    scrape_corrections,
    scrape_queries,
    scrape_review,
)

router = APIRouter()


def _guard(call):
    try:
        return call()
    except KeyError as exc:
        raise ApiException(404, "NOT_FOUND", "Review item not found") from exc
    except RevisionConflict as exc:
        raise ApiException(409, "REVISION_CONFLICT", str(exc)) from exc
    except ValueError as exc:
        raise ApiException(422, "SCRAPE_VALIDATION", str(exc)) from exc


def _launch_analysis(body: AnalyzeIn, request: Request, mgr) -> RunOut:
    def work(session, reporter):
        reporter.begin(1, "Inspecting public job page")
        draft = scrape_review.analyze_url(
            session, body.url, body.limits, checkpoint=reporter.checkpoint
        )
        reporter.step(1)
        return {"draftId": draft.id}

    return launch(mgr, "scrapeAnalyze", session_work(get_engine(request), work))


@router.post("/scrape/drafts", response_model=RunOut, status_code=202)
def analyze(body: AnalyzeIn, request: Request, mgr=Depends(get_run_manager)):
    return _launch_analysis(body, request, mgr)


@router.get("/scrape/drafts/{draft_id}", response_model=DraftOut)
def get_draft(draft_id: str, session: Session = Depends(get_session)):
    return DraftOut.model_validate(
        _guard(lambda: scrape_queries.get_draft(session, draft_id))
    )


@router.patch("/scrape/drafts/{draft_id}", response_model=DraftOut)
def patch_draft(
    draft_id: str, body: DraftPatchIn, session: Session = Depends(get_session)
):
    return DraftOut.model_validate(
        _guard(
            lambda: scrape_review.patch_draft(
                session,
                draft_id,
                body.expected_revision,
                plan=body.plan,
                limits=body.limits,
                samples=body.samples,
            )
        )
    )


@router.post(
    "/scrape/drafts/{draft_id}/validate", response_model=RunOut, status_code=202
)
def validate(
    draft_id: str, body: RevisionIn, request: Request, mgr=Depends(get_run_manager)
):
    def work(session, reporter):
        reporter.begin(1, "Checking extraction rules")
        draft = scrape_review.revalidate_draft(
            session, draft_id, body.expected_revision, checkpoint=reporter.checkpoint
        )
        reporter.step(1)
        return {"draftId": draft.id, "revision": draft.revision}

    return launch(mgr, "scrapeValidate", session_work(get_engine(request), work))


@router.post("/scrape/drafts/{draft_id}/approve", response_model=ApprovalResultOut)
def approve(draft_id: str, body: ApproveIn, session: Session = Depends(get_session)):
    return ApprovalResultOut.model_validate(
        _guard(
            lambda: scrape_review.approve_draft(
                session, draft_id, body.expected_revision, body.selected_keys
            )
        )
    )


@router.get("/scrape/sources", response_model=list[DraftOut])
def sources(session: Session = Depends(get_session)):
    return [DraftOut.model_validate(item) for item in scrape_review.list_sources(session)]


@router.get("/scrape/sources/{source_id}/revisions", response_model=list[DraftOut])
def revisions(source_id: str, session: Session = Depends(get_session)):
    return [
        DraftOut.model_validate(item)
        for item in scrape_queries.source_revisions(session, source_id)
    ]


@router.post("/scrape/sources/{source_id}/pull", response_model=RunOut, status_code=202)
def pull(
    source_id: str,
    request: Request,
    mgr=Depends(get_run_manager),
    refresh: bool = False,
):
    def work(session, reporter):
        reporter.begin(1, "Checking public job board")
        result = scrape_review.pull_source(
            session, source_id, checkpoint=reporter.checkpoint, refresh=refresh
        )
        reporter.step(1)
        return result.model_dump(mode="json", by_alias=True)

    return launch(
        mgr,
        "scrapePull",
        session_work(get_engine(request), work),
        singleton_key=f"scrape:{source_id}",
    )


@router.post(
    "/scrape/sources/{source_id}/relearn", response_model=RunOut, status_code=202
)
def relearn(
    source_id: str,
    request: Request,
    session: Session = Depends(get_session),
    mgr=Depends(get_run_manager),
):
    url, limits = _guard(
        lambda: scrape_queries.source_analysis_request(session, source_id)
    )
    return _launch_analysis(AnalyzeIn(url=url, limits=limits), request, mgr)


@router.post("/scrape/sources/{source_id}/rollback", response_model=DraftOut)
def rollback(source_id: str, body: RollbackIn, session: Session = Depends(get_session)):
    return DraftOut.model_validate(
        _guard(
            lambda: scrape_review.rollback_source(
                session, source_id, body.revision, body.expected_revision
            )
        )
    )


@router.get(
    "/jobs/{job_id}/source-observations", response_model=list[ObservationOut]
)
def observations(job_id: int, session: Session = Depends(get_session)):
    return [
        ObservationOut.model_validate(item)
        for item in scrape_queries.job_observations(session, job_id)
    ]


@router.get("/jobs/{job_id}/source-overrides", response_model=list[OverrideOut])
def get_overrides(job_id: int, session: Session = Depends(get_session)):
    return [
        OverrideOut.model_validate(item)
        for item in _guard(lambda: scrape_queries.job_overrides(session, job_id))
    ]


@router.put(
    "/jobs/{job_id}/source-overrides/{field}", response_model=OverrideRevisionOut
)
def set_override(
    job_id: int,
    field: FieldName,
    body: OverridePatchIn,
    session: Session = Depends(get_session),
):
    return OverrideRevisionOut(
        revision=_guard(
            lambda: scrape_corrections.set_job_override(
                session, job_id, field, OverridePatch.model_validate(body.model_dump())
            )
        )
    )


@router.delete(
    "/jobs/{job_id}/source-overrides/{field}", response_model=OverrideRevisionOut
)
def clear_override(
    job_id: int,
    field: FieldName,
    expected_revision: int,
    session: Session = Depends(get_session),
):
    return OverrideRevisionOut(
        revision=_guard(
            lambda: scrape_corrections.clear_job_override(
                session, job_id, field, expected_revision
            )
        )
    )


@router.post("/scrape/sources/{source_id}/edit", response_model=DraftOut)
def edit(source_id: str, session: Session = Depends(get_session)):
    return DraftOut.model_validate(
        _guard(lambda: scrape_review.edit_source(session, source_id))
    )


@router.get(
    "/scrape/snapshots/{snapshot_id}/elements", response_model=list[SnapshotElement]
)
def elements(snapshot_id: str, session: Session = Depends(get_session)):
    return _guard(lambda: scrape_review.snapshot_elements(session, snapshot_id))


@router.patch("/scrape/sources/{source_id}", response_model=DraftOut)
def source_state(
    source_id: str, body: SourceStateIn, session: Session = Depends(get_session)
):
    return DraftOut.model_validate(
        _guard(
            lambda: scrape_review.set_source_enabled(
                session, source_id, body.expected_revision, body.enabled
            )
        )
    )
