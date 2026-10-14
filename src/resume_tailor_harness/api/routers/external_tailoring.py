"""Tenant-scoped authoring context, free preflight, and reviewed submission."""

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from resume_tailor_harness.api.deps import (
    get_engine,
    get_profile_dir,
    get_run_manager,
    get_session,
)
from resume_tailor_harness.api.errors import ApiException
from resume_tailor_harness.api.runs.launch import launch, session_work
from resume_tailor_harness.api.runs.manager import RunManager
from resume_tailor_harness.api.schemas.external_tailoring import (
    AuthoringContextOut,
    DraftValidationOut,
    ExternalDraftIn,
)
from resume_tailor_harness.api.schemas.runs import RunOut
from resume_tailor_harness.services import external_tailoring as service

router = APIRouter(tags=["external-tailoring"])


def _call(fn, *args):
    try:
        return fn(*args)
    except service.ExternalTailoringError as exc:
        status = (
            404
            if exc.code == "NOT_FOUND"
            else 409
            if exc.code == "CONTEXT_STALE"
            else 422
        )
        raise ApiException(status, exc.code, str(exc)) from exc


@router.get("/jobs/{job_id}/authoring-context", response_model=AuthoringContextOut)
def context(job_id: int, request: Request, session: Session = Depends(get_session)):
    return _call(
        service.authoring_context,
        session,
        job_id,
        get_profile_dir(request) / "facts.json",
    )


@router.post(
    "/jobs/{job_id}/external-resume/validate", response_model=DraftValidationOut
)
def validate(
    job_id: int,
    body: ExternalDraftIn,
    request: Request,
    session: Session = Depends(get_session),
):
    return _call(
        service.validate_draft,
        session,
        job_id,
        get_profile_dir(request) / "facts.json",
        body.content,
        body.context_revision,
    )


@router.post("/jobs/{job_id}/external-resume", response_model=RunOut, status_code=202)
def submit(
    job_id: int,
    body: ExternalDraftIn,
    request: Request,
    session: Session = Depends(get_session),
    mgr: RunManager = Depends(get_run_manager),
):
    facts_path = get_profile_dir(request) / "facts.json"
    _call(
        service.validate_draft,
        session,
        job_id,
        facts_path,
        body.content,
        body.context_revision,
    )

    def work(worker_session, reporter):
        reporter.step(0, label="Reviewing external resume")
        return service.submit_draft(
            worker_session,
            job_id,
            facts_path,
            body.content,
            body.context_revision,
            body.agent,
            reporter=reporter,
        )

    return launch(
        mgr,
        "tailor",
        session_work(get_engine(request), work),
        singleton_key=f"external-resume:{job_id}",
        singleton_conflict="raise",
        meta={"jobId": job_id, "origin": "external"},
    )
