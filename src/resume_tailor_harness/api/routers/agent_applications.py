"""Authenticated, tenant-scoped application preparation for agent harnesses."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlmodel import Session

from resume_tailor_harness.api.deps import (
    get_config_store,
    get_profile_dir,
    get_session,
)
from resume_tailor_harness.api.errors import ApiException, ErrorResponse
from resume_tailor_harness.api.schemas.agent_applications import (
    ApplicationContextOut,
    ApplicationJobOut,
    ApplicationProfileOut,
    ApplicationProfileUpdate,
    ApplicationQuestionCreate,
    ApplicationQuestionOut,
    ApplicationQuestionUpdate,
)
from resume_tailor_harness.api.schemas.base import Page
from resume_tailor_harness.services import agent_applications as service


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    tags=["Agent applications"],
    dependencies=[Depends(_private)],
    responses={code: {"model": ErrorResponse} for code in (401, 404, 409, 422)},
)


@contextmanager
def _errors() -> Iterator[None]:
    try:
        yield
    except service.ApplicationWorkflowError as exc:
        raise ApiException(
            404 if exc.code == "NOT_FOUND" else 409, exc.code, str(exc)
        ) from exc


@router.get("/application-jobs", response_model=Page[ApplicationJobOut])
def list_application_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, alias="pageSize", ge=1, le=200),
    session: Session = Depends(get_session),
):
    return service.list_application_jobs(session, page=page, page_size=page_size)


@router.get("/jobs/{job_id}/application-context", response_model=ApplicationContextOut)
def application_context(
    job_id: int, request: Request, session: Session = Depends(get_session)
):
    with _errors():
        return service.application_context(
            session,
            job_id,
            get_config_store(request),
            get_profile_dir(request) / "facts.json",
        )


@router.get("/application-profile", response_model=ApplicationProfileOut)
def get_profile(request: Request):
    return service.read_profile(get_config_store(request))


@router.patch("/application-profile", response_model=ApplicationProfileOut)
def update_profile(body: ApplicationProfileUpdate, request: Request):
    with _errors():
        return service.update_profile(get_config_store(request), body)


@router.get("/application-questions", response_model=Page[ApplicationQuestionOut])
def list_questions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, alias="pageSize", ge=1, le=200),
    job_id: int | None = Query(None, alias="jobId", ge=1),
    status: Literal["unanswered", "answered"] | None = None,
    session: Session = Depends(get_session),
):
    with _errors():
        return service.list_questions(
            session, page=page, page_size=page_size, job_id=job_id, status=status
        )


@router.post("/application-questions", response_model=ApplicationQuestionOut)
def create_question(
    body: ApplicationQuestionCreate, session: Session = Depends(get_session)
):
    with _errors():
        return service.create_question(session, body)


@router.patch(
    "/application-questions/{question_id}", response_model=ApplicationQuestionOut
)
def update_question(
    question_id: int,
    body: ApplicationQuestionUpdate,
    session: Session = Depends(get_session),
):
    with _errors():
        return service.update_question(session, question_id, body)


@router.get(
    "/application-questions/{question_id}", response_model=ApplicationQuestionOut
)
def get_question(question_id: int, session: Session = Depends(get_session)):
    with _errors():
        return service.get_question(session, question_id)
