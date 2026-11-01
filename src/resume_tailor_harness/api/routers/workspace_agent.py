"""Human review endpoints. None is supplied to a model as a tool."""

from fastapi import APIRouter, Query, Request
from sqlmodel import Session, col, select

from resume_tailor_harness.api.deps import get_config_store, get_data_dir, get_engine
from resume_tailor_harness.api.errors import ApiException
from resume_tailor_harness.api.schemas.workspace_agent import (
    ProposalOut,
    ProposalPage,
    ReviewIn,
)
from resume_tailor_harness.tenancy.context import current_context
from resume_tailor_harness.workspace_agent.actions import proposal_view, resolve_plan
from resume_tailor_harness.workspace_agent.models import Surface
from resume_tailor_harness.workspace_agent.tables import WorkspaceProposal

router = APIRouter(tags=["Workspace agent review"])


@router.get("/workspace-agent/proposals", response_model=ProposalPage)
def list_proposals(
    request: Request,
    surface: Surface,
    session_id: str = Query(alias="sessionId", min_length=1, max_length=100),
    offset: int = Query(0, ge=0),
):
    engine = get_engine(request)
    with Session(engine) as session:
        rows = session.exec(
            select(WorkspaceProposal)
            .where(
                WorkspaceProposal.surface == surface,
                WorkspaceProposal.session_id == session_id,
            )
            .order_by(col(WorkspaceProposal.created_at).desc())
            .offset(offset)
            .limit(21)
        ).all()
    return {
        "proposals": [proposal_view(engine, row.id) for row in rows[:20]],
        "next_offset": offset + 20 if len(rows) > 20 else None,
    }


@router.post(
    "/workspace-agent/proposals/{proposal_id}/review", response_model=ProposalOut
)
def review_proposal(proposal_id: str, body: ReviewIn, request: Request):
    # PAT-authenticated external agents cannot impersonate this in-app review action.
    # Local mode is loopback-only; hosted mode uses its authenticated browser session.
    if request.headers.get("authorization"):
        raise ApiException(
            403, "HUMAN_REVIEW_REQUIRED", "Review changes in the application"
        )
    context = current_context()
    try:
        return resolve_plan(
            get_engine(request),
            get_data_dir(request),
            get_config_store(request),
            proposal_id,
            digest=body.digest,
            action_ids=body.action_ids,
            decision=body.decision,
            actor=context.user_id if context else "local-user",
        )
    except ValueError as exc:
        raise ApiException(409, "WORKSPACE_REVIEW_CONFLICT", str(exc)) from exc
