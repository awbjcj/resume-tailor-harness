"""Read-only command schemas, validation, revision checks and review previews."""

import json
import uuid
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from resume_tailor_harness.services import application_events, board
from resume_tailor_harness.services.config_store import YamlConfigStore
from resume_tailor_harness.tracking.tables import (
    ApplicationQuestion,
    ApplicationStatus,
    Job,
    JobStatus,
)
from resume_tailor_harness.workspace_agent.models import (
    WorkspaceChange,
    WorkspacePlan,
    is_file_action,
)
from resume_tailor_harness.workspace_agent.reads import job_snapshot, record, revision


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
        "job.update": TypeAdapter(JobInput | StageInput).json_schema(),
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
                select(ApplicationQuestion)
                .where(col(ApplicationQuestion.job_id).is_(None))
                .order_by(col(ApplicationQuestion.id))
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


def review_revision(snapshot: Any, change: WorkspaceChange) -> str:
    """Bind approval to the records used by this preview, not unrelated notes."""
    if change.operation.startswith("note.") or change.operation == "preparation.save":
        snapshot = {
            "job": snapshot["job"],
            "note": _target(snapshot["notes"], change.target_id)
            if change.operation in {"note.update", "note.delete"}
            else None,
        }
    elif change.operation == "artifact.select":
        kind = change.values["kind"]
        field = "resume_version_id" if kind == "resume" else "cover_letter_id"
        snapshot = {
            "job": snapshot["job"],
            "selected": snapshot["application"].get(field),
            "document": _target(
                snapshot["resumes" if kind == "resume" else "cover_letters"],
                change.target_id,
            ),
        }
    return revision(snapshot)


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
            # Only the incoming fields cross the API boundary. SQLite returns
            # stored UTC timestamps without an offset; they are not user input.
            payload = {
                **(before or {}),
                **model.model_validate(values).model_dump(exclude_unset=True),
            }
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
    elif op == "artifact.select":
        field = "resume_version_id" if values["kind"] == "resume" else "cover_letter_id"
        before = {field: snap["application"].get(field)}
        after = {field: change.target_id}
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
    elif op == "job.update" and "status" in values:
        after = board.stage_changes(snap["job"]["status"], values["status"])
        before = {key: snap["job"].get(key) for key in after}
    elif op == "job.update":
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
        "expected_revision": review_revision(snap, change),
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
        (
            c.operation.split(".")[0],
            c.values.get("kind") if c.operation.startswith("artifact.") else None,
            c.job_id,
            c.target_id,
        )
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
