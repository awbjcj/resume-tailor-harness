"""Apply validated commands through domain services, outside the model loop."""

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from resume_tailor_harness.services import application_events, board
from resume_tailor_harness.services.config_store import YamlConfigStore
from resume_tailor_harness.tracking.tables import (
    ApplicationQuestion,
    Job,
    JobStatus,
    utcnow,
)
from resume_tailor_harness.workspace_agent.commands import snapshot_for
from resume_tailor_harness.workspace_agent.models import WorkspaceChange
from resume_tailor_harness.workspace_agent.reads import record, revision
from resume_tailor_harness.workspace_agent.tables import WorkspaceNote


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
