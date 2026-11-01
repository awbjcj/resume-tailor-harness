"""Validate proposals without effects; execute immutable human-approved actions."""

import json
import uuid
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from resume_tailor_harness.services import application_events, board
from resume_tailor_harness.services.config_store import YamlConfigStore
from resume_tailor_harness.tracking.tables import (
    ApplicationQuestion,
    ApplicationStatus,
    Job,
    JobStatus,
    utcnow,
)
from resume_tailor_harness.workspace_agent.models import WorkspaceChange, WorkspacePlan
from resume_tailor_harness.workspace_agent.reads import job_snapshot, record, revision
from resume_tailor_harness.workspace_agent.tables import (
    WorkspaceActionReceipt,
    WorkspaceNote,
    WorkspaceProposal,
)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JobInput(Input):
    company: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=2048)
    jd_text: str | None = Field(default=None, max_length=100000)


class ApplicationInput(Input):
    status: ApplicationStatus
    notes: str | None = Field(default=None, max_length=20000)


class StageInput(Input):
    status: JobStatus


class NoteInput(Input):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)


class ArtifactInput(Input):
    kind: Literal["resume", "cover_letter"]


class QuestionAnswerInput(Input):
    answer: str | None = Field(max_length=4000)


def schemas() -> dict[str, Any]:
    from resume_tailor_harness.api.schemas.application_events import (
        ApplicationEventCreate,
        ApplicationEventUpdate,
    )
    from resume_tailor_harness.api.schemas.agent_applications import (
        ApplicationProfilePatch,
        ApplicationQuestionCreate,
    )
    from resume_tailor_harness.profile.conversation import ProfileChangeSet
    from resume_tailor_harness.api.schemas.config import SearchConfigDoc

    return {
        "job.create": JobInput.model_json_schema(),
        "job.update": {
            "oneOf": [JobInput.model_json_schema(), StageInput.model_json_schema()]
        },
        "application.update": ApplicationInput.model_json_schema(),
        "note.create": NoteInput.model_json_schema(),
        "note.update": NoteInput.model_json_schema(),
        "preparation.save": NoteInput.model_json_schema(),
        "event.create": ApplicationEventCreate.model_json_schema(),
        "event.update": ApplicationEventUpdate.model_json_schema(),
        "profile.change": ProfileChangeSet.model_json_schema(),
        "application_profile.update": ApplicationProfilePatch.model_json_schema(),
        "question.create": ApplicationQuestionCreate.model_json_schema(),
        "question.update": QuestionAnswerInput.model_json_schema(),
        "artifact.select": ArtifactInput.model_json_schema(),
        "artifact.delete": ArtifactInput.model_json_schema(),
        "search.update": SearchConfigDoc.model_json_schema(),
        "empty_values": [
            "job.archive",
            "job.restore",
            "job.delete",
            "event.delete",
            "note.delete",
            "question.delete",
        ],
    }


def _validate_values(model: type[BaseModel], values: dict) -> dict:
    # Older API schemas ignore unknown fields. The agent command boundary must not.
    fields = set(model.model_fields) | {
        f.alias for f in model.model_fields.values() if f.alias
    }
    if set(values) - fields:
        raise ValueError("Unknown fields: " + ", ".join(sorted(set(values) - fields)))
    return model.model_validate(values).model_dump(mode="json", exclude_unset=True)


def _target(rows: list[dict], target_id: int | None) -> dict:
    row = next((row for row in rows if row["id"] == target_id), None)
    if row is None:
        raise ValueError("Unknown target or target does not belong to this job")
    return row


def _global_snapshot(
    session: Session, root: Path, config: YamlConfigStore, operation: str
) -> Any:
    if operation == "profile.change":
        from resume_tailor_harness.profile.conversation import profile_revision

        return profile_revision(root / "profile")
    if operation == "application_profile.update":
        from resume_tailor_harness.services.agent_applications import read_profile

        return read_profile(config).model_dump(mode="json")
    if operation == "search.update":
        return config.get("search").model_dump(mode="json")
    if operation.startswith("question."):
        return [
            record(row)
            for row in session.exec(
                select(ApplicationQuestion).order_by(col(ApplicationQuestion.id))
            ).all()
        ]
    if operation == "job.create":
        # Detect concurrent additions/ingestion before the approved create.
        return [
            (job.id, job.url, job.content_fingerprint, job.dedup_key)
            for job in session.exec(select(Job).order_by(col(Job.id))).all()
        ]
    raise ValueError("This action requires a job_id")


def snapshot_for(
    session: Session, root: Path, config: YamlConfigStore, change: WorkspaceChange
) -> Any:
    if change.job_id is not None and change.operation not in {
        "profile.change",
        "application_profile.update",
        "search.update",
    }:
        return job_snapshot(session, change.job_id)
    return _global_snapshot(session, root, config, change.operation)


def prepare_change(
    session: Session,
    root: Path,
    config: YamlConfigStore,
    change: WorkspaceChange,
    user_text: str,
) -> dict:
    from resume_tailor_harness.api.schemas.application_events import (
        ApplicationEventCreate,
        ApplicationEventUpdate,
    )
    from resume_tailor_harness.api.schemas.agent_applications import (
        ApplicationProfilePatch,
        ApplicationQuestionCreate,
    )
    from resume_tailor_harness.api.schemas.config import SearchConfigDoc
    from resume_tailor_harness.profile.conversation import (
        ProfileChangeSet,
        prepare_changes,
    )

    op, values = change.operation, change.values
    global_ops = {
        "job.create",
        "profile.change",
        "application_profile.update",
        "search.update",
    }
    if op in global_ops and (change.job_id is not None or change.target_id is not None):
        raise ValueError("This operation does not take a job or target id")
    if (
        op not in global_ops
        and not op.startswith("question.")
        and change.job_id is None
    ):
        raise ValueError("A saved job_id is required")
    if len(json.dumps(values, ensure_ascii=False)) > 120000:
        raise ValueError("Change is too large")
    for url in change.citations:
        if (
            len(url) > 2048
            or urlsplit(url).scheme not in {"http", "https"}
            or not urlsplit(url).hostname
        ):
            raise ValueError("Citations must be public web URLs")
    snap = snapshot_for(session, root, config, change)
    before: Any = None
    prepared: dict = {}
    if op in {"job.create", "job.update"}:
        values = _validate_values(
            StageInput if "status" in values else JobInput, values
        )
        if not values:
            raise ValueError("Supply changed fields")
        if "jd_text" in values and (
            not isinstance(values["jd_text"], str) or not values["jd_text"].strip()
        ):
            raise ValueError("Job description cannot be empty")
        if values.get("url") and (
            urlsplit(values["url"]).scheme not in {"http", "https"}
            or not urlsplit(values["url"]).hostname
        ):
            raise ValueError("Job URL must use http or https")
        if op == "job.create":
            if (
                change.job_id is not None
                or "status" in values
                or not str(values.get("jd_text") or "").strip()
            ):
                raise ValueError(
                    "Creating a job requires jd_text and no existing job_id/status"
                )
        else:
            before = {key: snap["job"].get(key) for key in values}
            if "status" not in values and (
                snap["has_progress"] or snap["job"]["source"] != "manual"
            ):
                raise ValueError(
                    "Posting corrections require an unprogressed manual job; preserve imported evidence and use a note otherwise"
                )
    elif op == "application.update":
        values = _validate_values(ApplicationInput, values)
        before = snap["application"]
    elif op in {"note.create", "note.update", "preparation.save"}:
        values = _validate_values(NoteInput, values)
        if op == "note.update":
            before = _target(snap["notes"], change.target_id)
            if before["deleted"]:
                raise ValueError("Note has been removed")
    elif op.startswith("event."):
        before = (
            _target(snap["events"], change.target_id) if op != "event.create" else None
        )
        if op != "event.delete":
            model = (
                ApplicationEventCreate
                if op == "event.create"
                else ApplicationEventUpdate
            )
            values = _validate_values(model, values)
            merged = {**(before or {}), **values}
            payload = ApplicationEventCreate.model_validate(merged).model_dump()
            try:
                application_events._validate(payload)
            except application_events.EventValidationError as exc:
                raise ValueError(str(exc)) from exc
    elif op == "profile.change":
        draft = prepare_changes(
            root / "profile",
            ProfileChangeSet.model_validate(values),
            user_text,
            source_ref="workspace-conversation",
        )
        prepared["profile_draft"] = draft.model_dump(mode="json")
        before = [p.model_dump(mode="json") for p in draft.previews]
    elif op == "application_profile.update":
        values = _validate_values(ApplicationProfilePatch, values)
        before = snap["profile"]
        prepared["file_revision"] = snap["revision"]
    elif op == "question.create":
        values = _validate_values(ApplicationQuestionCreate, values)
        if values.get("job_id") != change.job_id:
            raise ValueError("Question job must match the reviewed target")
    elif op in {"question.update", "question.delete"}:
        before = _target(snap["questions"] if change.job_id else snap, change.target_id)
        if op == "question.update":
            if set(values) != {"answer"} or (
                values["answer"] is not None
                and (
                    not isinstance(values["answer"], str)
                    or not 1 <= len(values["answer"].strip()) <= 4000
                )
            ):
                raise ValueError("Supply only answer (text or null)")
    elif op.startswith("artifact."):
        if set(values) != {"kind"} or values["kind"] not in {"resume", "cover_letter"}:
            raise ValueError("Artifact kind must be resume or cover_letter")
        before = _target(
            snap["resumes" if values["kind"] == "resume" else "cover_letters"],
            change.target_id,
        )
        if (
            op == "artifact.delete"
            and snap["application"].get(
                f"{values['kind']}_id"
                if values["kind"] == "cover_letter"
                else "resume_version_id"
            )
            == change.target_id
        ):
            raise ValueError(
                "Selected documents must be kept; select a replacement first"
            )
    elif op == "search.update":
        patch = _validate_values(SearchConfigDoc, values)
        values = _validate_values(SearchConfigDoc, {**snap, **patch})
        before = snap
    elif op in {"job.archive", "job.restore", "job.delete"}:
        before = snap["job"]
        if op == "job.delete" and (
            snap["has_progress"] or any(not n["deleted"] for n in snap["notes"])
        ):
            raise ValueError("Job has saved work. Archive it instead of deleting")
    elif op == "note.delete":
        before = _target(snap["notes"], change.target_id)
    if (op.endswith(".delete") and op != "artifact.delete") or op in {
        "job.archive",
        "job.restore",
    }:
        if values:
            raise ValueError("This operation takes empty values")
    after = values
    if op in {"job.archive", "job.restore"}:
        before = {"archived": bool(snap["job"]["archived_at"])}
        after = {"archived": op == "job.archive"}
    elif op.endswith(".delete"):
        after = {"deleted": True}
    elif op == "profile.change":
        before = [p["before"] for p in prepared["profile_draft"]["previews"]]
        after = [p["after"] for p in prepared["profile_draft"]["previews"]]
    elif op in {"event.create", "event.update"}:
        from resume_tailor_harness.tracking.event_vocab import KIND_IMPLIES_STATUS
        from resume_tailor_harness.tracking.status_rules import (
            advance_application_status,
        )

        current_status = snap["application"].get("status", "ready")
        kind = values.get("kind", (before or {}).get("kind"))
        implied = KIND_IMPLIES_STATUS.get(str(kind))
        after = {
            **values,
            "application_status": advance_application_status(current_status, implied)
            if implied
            else current_status,
        }
    elif op == "job.update" and "status" not in values:
        after = {
            **values,
            "status": "raw",
            "criteria_json": None,
            "analysis_meta_json": None,
            "industry_pending": False,
            "reject_reason": None,
            "reject_category": None,
            "gate_override": False,
            "fit_score": None,
            "fit_rationale": None,
        }
        before = {key: snap["job"].get(key) for key in after}
    return {
        "id": uuid.uuid4().hex,
        "change": change.model_copy(update={"values": values}).model_dump(mode="json"),
        "expected_revision": revision(snap),
        "before": before,
        "after": after,
        **prepared,
    }


def prepare_plan(
    engine: Engine,
    root: Path,
    config: YamlConfigStore,
    plan: WorkspacePlan,
    user_text: str,
) -> dict:
    with Session(engine) as session:
        actions = [
            prepare_change(session, root, config, c, user_text) for c in plan.changes
        ]
    # File-backed effects have a separate recovery contract and must be reviewed alone.
    if len(actions) > 1 and any(
        is_file_action(a["change"]["operation"]) for a in actions
    ):
        raise ValueError(
            "Review profile or settings changes separately from other changes"
        )
    deleted_jobs = {c.job_id for c in plan.changes if c.operation == "job.delete"}
    for job_id in deleted_jobs:
        if sum(c.job_id == job_id for c in plan.changes) > 1:
            raise ValueError("Review a job deletion without other changes to that job")
    targets = [
        (c.operation.split(".")[0], c.job_id, c.target_id)
        for c in plan.changes
        if c.target_id is not None
    ]
    if len(targets) != len(set(targets)):
        raise ValueError("Combine changes to the same record into one reviewed action")
    # Avoid order-dependent previews (e.g. two events implying different statuses).
    singletons = []
    for change in plan.changes:
        op = change.operation
        if op.startswith("job.") and op != "job.create":
            singletons.append(("job", change.job_id))
        elif op in {"event.create", "event.update", "application.update"}:
            singletons.append(("application", change.job_id))
        elif op == "artifact.select":
            singletons.append((f"selected_{change.values['kind']}", change.job_id))
    if len(singletons) != len(set(singletons)):
        raise ValueError(
            "Review status changes or document selections for the same job separately"
        )
    return {
        "id": uuid.uuid4().hex,
        "title": plan.title,
        "actions": actions,
        "digest": revision(actions),
    }


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


def _execute_database(session: Session, change: WorkspaceChange, actor: str) -> dict:
    from resume_tailor_harness.api.schemas.application_events import (
        ApplicationEventCreate,
        ApplicationEventUpdate,
    )
    from resume_tailor_harness.api.schemas.agent_applications import (
        ApplicationQuestionCreate,
        ApplicationQuestionUpdate,
    )
    from resume_tailor_harness.services import agent_applications
    from resume_tailor_harness.services.discovery import add_job_from_text

    op, v, job_id, target = (
        change.operation,
        change.values,
        change.job_id,
        change.target_id,
    )
    if op == "job.create":
        existing_ids = set(session.exec(select(Job.id)).all())
        saved = add_job_from_text(session, **v)
        if saved is None or saved.id in existing_ids:
            raise ValueError(
                "Job already exists; read it before proposing another change"
            )
        return {"job_id": saved.id}
    if op == "question.create":
        return record(
            agent_applications.create_question(
                session, ApplicationQuestionCreate.model_validate(v)
            )
        )
    if op in {"question.update", "question.delete"}:
        row = session.get(ApplicationQuestion, target)
        if row is None or row.job_id != job_id:
            raise ValueError("Unknown question")
        if op == "question.delete":
            session.delete(row)
            return {"question_id": target, "deleted": True}
        assert row.id is not None
        return record(
            agent_applications.update_question(
                session,
                row.id,
                ApplicationQuestionUpdate(
                    revision=row.revision, answer=v["answer"], user_confirmed=True
                ),
            )
        )
    if job_id is None:
        raise ValueError("Job id is required")
    if op == "job.update":
        if "status" in v:
            return record(board.set_stage(session, job_id, v["status"]))
        from resume_tailor_harness.tracking.dedup import (
            compute_dedup_key,
            compute_content_fingerprint,
        )
        from resume_tailor_harness.tracking.repository import company_rename_collides

        job = session.get(Job, job_id)
        assert job is not None
        for key, value in v.items():
            setattr(job, key, value)
        job.dedup_key = compute_dedup_key(job.company, job.title)
        if company_rename_collides(session, existing=job, dedup_key=job.dedup_key):
            raise ValueError(
                "Another job has this company and title; review the duplicate first"
            )
        if (
            job.url
            and session.exec(
                select(Job).where(
                    Job.id != job_id, Job.url == job.url, col(Job.archived_at).is_(None)
                )
            ).first()
        ):
            raise ValueError("Another job already uses this URL")
        job.content_fingerprint = compute_content_fingerprint(job.jd_text)
        job.criteria_json = None
        job.analysis_meta_json = None
        job.industry_pending = False
        job.reject_reason = None
        job.reject_category = None
        job.gate_override = False
        job.fit_score = None
        job.fit_rationale = None
        job.status = JobStatus.raw.value
        session.add(job)
        return record(job)
    if op in {"job.archive", "job.restore"}:
        return record(board.set_archived(session, job_id, op == "job.archive"))
    if op == "job.delete":
        if not board.delete(session, job_id):
            raise ValueError("Job has progress and cannot be deleted")
        for note in session.exec(
            select(WorkspaceNote).where(WorkspaceNote.job_id == job_id)
        ).all():
            session.delete(note)
        return {"job_id": job_id, "deleted": True}
    if op == "application.update":
        return record(board.upsert_application(session, job_id, **v))
    if op.startswith("event."):
        if op == "event.create":
            return record(
                application_events.create_event(
                    session,
                    job_id,
                    ApplicationEventCreate.model_validate(v).model_dump(),
                )
            )
        if target is None:
            raise ValueError("Event id required")
        if op == "event.update":
            return record(
                application_events.update_event(
                    session,
                    job_id,
                    target,
                    ApplicationEventUpdate.model_validate(v).model_dump(
                        exclude_unset=True
                    ),
                )
            )
        return {
            "event_id": target,
            "deleted": application_events.delete_event(session, job_id, target),
        }
    if op.startswith("note.") or op == "preparation.save":
        note = session.get(WorkspaceNote, target) if target else None
        if op in {"note.create", "preparation.save"}:
            note = WorkspaceNote(
                job_id=job_id,
                kind="preparation" if op == "preparation.save" else "note",
                **v,
            )
        elif note is None or note.job_id != job_id:
            raise ValueError("Unknown note")
        else:
            note.revision += 1
            if op == "note.delete":
                note.deleted = True
            else:
                note.title, note.body = v["title"], v["body"]
        note.citations = change.citations
        note.updated_at = utcnow()
        note.history = [
            *note.history,
            {
                "revision": note.revision,
                "title": note.title,
                "body": note.body,
                "deleted": note.deleted,
                "citations": note.citations,
                "actor": actor,
                "at": note.updated_at.isoformat(),
            },
        ]
        session.add(note)
        session.flush()
        return {
            "note_id": note.id,
            "job_id": job_id,
            "revision": note.revision,
            "deleted": note.deleted,
        }
    if op.startswith("artifact."):
        if target is None:
            raise ValueError("Artifact id required")
        if op == "artifact.select":
            fn = (
                board.select_resume_version
                if v["kind"] == "resume"
                else board.select_cover_letter
            )
            return record(fn(session, job_id, target))
        fn = (
            board.delete_resume_versions
            if v["kind"] == "resume"
            else board.delete_cover_letters
        )
        result = fn(session, [target])
        if result.deleted != 1:
            raise ValueError("Artifact is selected or no longer exists")
        return {"artifact_id": target, "deleted": True}
    raise ValueError("Unsupported database action")


def is_file_action(operation: str) -> bool:
    return operation in {
        "profile.change",
        "application_profile.update",
        "search.update",
        "artifact.delete",
    }


def _execute_file(
    engine: Engine,
    root: Path,
    config: YamlConfigStore,
    action: dict,
    source_text: str,
    actor: str,
) -> dict:
    from resume_tailor_harness.api.schemas.agent_applications import (
        ApplicationProfileUpdate,
    )
    from resume_tailor_harness.services.agent_applications import update_profile
    from resume_tailor_harness.api.schemas.config import SearchConfigDoc
    from resume_tailor_harness.profile.conversation import CoachChangeDraft
    from resume_tailor_harness.services.profile_conversation import (
        apply_workspace_draft,
    )

    change = WorkspaceChange.model_validate(action["change"])
    if change.operation == "artifact.delete":
        with Session(engine) as session:
            if engine.dialect.name == "sqlite":
                session.execute(text("BEGIN IMMEDIATE"))
            if (
                revision(snapshot_for(session, root, config, change))
                != action["expected_revision"]
            ):
                raise ValueError("Workspace changed; request a fresh proposal")
            return _execute_database(session, change, actor)
    if change.operation == "profile.change":
        apply_workspace_draft(
            root / "profile",
            CoachChangeDraft.model_validate(action["profile_draft"]),
            source_text,
        )
        return {"profile": "updated"}
    if change.operation == "application_profile.update":
        # Content revision is checked again inside the config store's writer lock.
        expected = action["file_revision"]
        result = update_profile(
            config,
            ApplicationProfileUpdate.model_validate(
                {"revision": expected, "profile": change.values, "userConfirmed": True}
            ),
        )
        return {"revision": result.revision}
    expected = action["expected_revision"]

    def update(current):
        if revision(current.model_dump(mode="json")) != expected:
            raise ValueError("Settings changed; request a fresh proposal")
        return SearchConfigDoc.model_validate(change.values)

    config.update("search", update)
    return {"settings": "search", "updated": True}


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
