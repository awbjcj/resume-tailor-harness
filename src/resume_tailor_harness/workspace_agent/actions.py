"""Persist immutable proposals and coordinate approval, transactions and receipts."""

from datetime import timedelta, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from resume_tailor_harness.services.config_store import YamlConfigStore
from resume_tailor_harness.tracking.tables import utcnow
from resume_tailor_harness.workspace_agent.commands import (
    prepare_change,
    prepare_plan as prepare_plan,
    schemas as schemas,
    snapshot_for,
)
from resume_tailor_harness.workspace_agent.execution import (
    _execute_database,
    _execute_file,
)
from resume_tailor_harness.workspace_agent.models import WorkspaceChange, is_file_action
from resume_tailor_harness.workspace_agent.reads import (
    record,
    revision,
)
from resume_tailor_harness.workspace_agent.tables import (
    WorkspaceActionReceipt,
    WorkspaceProposal,
)


def save_plan(
    engine: Engine,
    plan: dict,
    *,
    surface: str,
    session_id: str,
    run_id: str,
    source_text: str,
) -> None:
    with Session(engine) as session:
        session.add(
            WorkspaceProposal(
                **plan,
                surface=surface,
                session_id=session_id,
                run_id=run_id,
                source_text=source_text,
                expires_at=utcnow() + timedelta(hours=24),
            )
        )
        session.commit()


class ActionSession(Session):
    """Keep legacy service commits inside the effect-and-receipt transaction."""

    def commit(self) -> None:
        self.flush()

    def finish(self) -> None:
        super().commit()


def resolve_plan(
    engine: Engine,
    root: Path,
    config: YamlConfigStore,
    proposal_id: str,
    *,
    digest: str,
    action_ids: list[str],
    decision: str,
    actor: str,
) -> dict:
    if (
        decision not in {"apply", "discard"}
        or not action_ids
        or len(set(action_ids)) != len(action_ids)
    ):
        raise ValueError("Choose distinct reviewed actions and apply or discard")
    file_action: tuple[dict, str] | None = None
    with ActionSession(engine) as session:
        if engine.dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))
        proposal = session.get(WorkspaceProposal, proposal_id)
        if proposal is None:
            raise ValueError("Unknown proposal")
        if digest != proposal.digest or revision(proposal.actions) != digest:
            raise ValueError("Proposal no longer matches the reviewed changes")
        selected = [a for a in proposal.actions if a["id"] in action_ids]
        if len(selected) != len(action_ids):
            raise ValueError("Unknown action")
        pending = []
        for action in selected:
            receipt = session.get(WorkspaceActionReceipt, action["id"])
            if receipt:
                expected = "applied" if decision == "apply" else "discarded"
                if receipt.state != expected:
                    raise ValueError(
                        "Action already resolved or outcome unknown; read its receipt"
                    )
                continue
            if (
                decision == "apply"
                and proposal.expires_at.replace(tzinfo=timezone.utc) <= utcnow()
            ):
                raise ValueError("Proposal expired; request a fresh preview")
            pending.append(action)
        for action in pending:
            change = WorkspaceChange.model_validate(action["change"])
            if (
                decision == "apply"
                and revision(snapshot_for(session, root, config, change))
                != action["expected_revision"]
            ):
                raise ValueError(
                    "Workspace changed; request a fresh proposal before applying"
                )
            # Revalidate the immutable payload against current domain rules before any effect.
            if decision == "apply":
                prepare_change(session, root, config, change, proposal.source_text)
        for action in pending:
            change = WorkspaceChange.model_validate(action["change"])
            result: dict = {}
            state = "discarded"
            if decision == "apply":
                if is_file_action(change.operation):
                    state = "outcome_unknown"
                    file_action = action, proposal.source_text
                else:
                    result = _execute_database(session, change, actor)
                    state = "applied"
            session.add(
                WorkspaceActionReceipt(
                    id=action["id"],
                    proposal_id=proposal_id,
                    state=state,
                    approved_by=actor,
                    result=result,
                )
            )
        session.finish()
    if file_action:
        action, source_text = file_action
        # The durable unknown marker precedes the file effect: a crash never grants a blind retry.
        result = _execute_file(engine, root, config, action, source_text, actor)
        with Session(engine) as session:
            receipt = session.get(WorkspaceActionReceipt, action["id"])
            assert receipt is not None
            receipt.state, receipt.result = "applied", result
            session.add(receipt)
            session.commit()
    if decision == "apply":
        # Files are a separate store; cleanup is idempotent after the DB receipt.
        # Replayed approvals also complete any interrupted session cleanup.
        from resume_tailor_harness.interview.store import delete_sessions_for_job
        from resume_tailor_harness.career_lab.store import (
            delete_sessions_for_job as delete_lab_sessions,
        )

        for action in selected:
            if action["change"]["operation"] == "job.delete":
                job_id = action["change"]["job_id"]
                delete_sessions_for_job(root / "interview", job_id)
                delete_lab_sessions(root / "career-lab", job_id)
    return proposal_view(engine, proposal_id)


def proposal_view(engine: Engine, proposal_id: str) -> dict:
    with Session(engine) as session:
        row = session.get(WorkspaceProposal, proposal_id)
        if row is None:
            raise ValueError("Unknown proposal")
        receipts = {
            r.id: record(r)
            for r in session.exec(
                select(WorkspaceActionReceipt).where(
                    WorkspaceActionReceipt.proposal_id == row.id
                )
            ).all()
        }
        return {
            "id": row.id,
            "title": row.title,
            "digest": row.digest,
            "surface": row.surface,
            "session_id": row.session_id,
            "created_at": row.created_at.isoformat(),
            "expires_at": row.expires_at.isoformat(),
            "actions": [
                {
                    "id": a["id"],
                    "change": a["change"],
                    "before": a["before"],
                    "after": a["after"],
                    "receipt": receipts.get(a["id"]),
                }
                for a in row.actions
            ],
        }
