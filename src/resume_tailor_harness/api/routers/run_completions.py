from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session, select

from resume_tailor_harness.api.deps import (
    get_career_lab_dir,
    get_interview_dir,
    get_profile_dir,
    get_scout_dir,
    get_session,
)
from resume_tailor_harness.api.errors import ApiException
from resume_tailor_harness.api.schemas.run_completions import (
    RunCompletionOut,
    RunCompletionsReadOut,
)
from resume_tailor_harness.services.run_completions import (
    list_run_completions,
    clear_run_history,
    operation_logs,
    mark_all_run_completions_read,
    mark_run_completion_read,
)
from resume_tailor_harness.services.run_results import completion_results
from resume_tailor_harness.tracking.tables import RunCompletion

router = APIRouter()


def _results(
    request: Request, session: Session, rows: list[RunCompletion]
) -> list[RunCompletionOut]:
    checked: dict[tuple[str, str], bool] = {}

    def session_exists(kind: str, session_id: str) -> bool:
        family = kind.rsplit("-", 1)[0]
        key = (family, session_id)
        if key in checked:
            return checked[key]
        try:
            if kind.startswith("profile-coach-"):
                from resume_tailor_harness.profile.coach_store import load_session

                load_session(get_profile_dir(request), session_id)
            elif kind.startswith("career-lab-"):
                from resume_tailor_harness.career_lab.store import load_session

                load_session(get_career_lab_dir(request), session_id)
            elif kind.startswith("mock-interview-"):
                from resume_tailor_harness.interview.store import load_session

                load_session(get_interview_dir(request), session_id)
            elif kind.startswith("scout-"):
                from resume_tailor_harness.discovery.scout_store import load_session

                load_session(get_scout_dir(request).parent, session_id)
            else:
                return False
        except (ValueError, OSError):
            checked[key] = False
        else:
            checked[key] = True
        return checked[key]

    return completion_results(session, rows, session_exists=session_exists)


@router.get("/run-completions", response_model=list[RunCompletionOut])
def list_completions(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    unread_only: bool = Query(default=False),
    surface: Literal["operations", "notifications"] = "operations",
    session: Session = Depends(get_session),
):
    return _results(
        request,
        session,
        list_run_completions(
            session, limit=limit, unread_only=unread_only, surface=surface
        ),
    )


@router.get("/run-completions/by-run/{run_id}", response_model=RunCompletionOut)
def result_for_run(
    run_id: str, request: Request, session: Session = Depends(get_session)
):
    row = session.exec(
        select(RunCompletion).where(RunCompletion.run_id == run_id)
    ).first()
    if row is None:
        raise ApiException(404, "NOT_FOUND", "Completed operation not found")
    return _results(request, session, [row])[0]


@router.post("/run-completions/{completion_id}/read", response_model=RunCompletionOut)
def mark_read(
    completion_id: int, request: Request, session: Session = Depends(get_session)
):
    row = mark_run_completion_read(session, completion_id)
    if row is None:
        raise ApiException(
            404, "NOT_FOUND", f"Run completion #{completion_id} not found"
        )
    return _results(request, session, [row])[0]


@router.post("/run-completions/read-all", response_model=RunCompletionsReadOut)
def mark_all_read(session: Session = Depends(get_session)):
    return RunCompletionsReadOut(marked_read=mark_all_run_completions_read(session))


@router.delete("/run-completions", response_model=dict[str, int])
def clear_operations(session: Session = Depends(get_session)):
    return {"cleared": clear_run_history(session, surface="operations")}


@router.get(
    "/run-completions/{completion_id}/logs", response_model=list[dict[str, str]]
)
def get_logs(completion_id: int, session: Session = Depends(get_session)):
    entries = operation_logs(session, completion_id)
    if entries is None:
        raise ApiException(404, "NOT_FOUND", "Operation history not found")
    return entries
