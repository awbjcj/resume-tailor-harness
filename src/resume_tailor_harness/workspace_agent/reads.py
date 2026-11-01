"""Bounded, side-effect-free projections of the owning workspace stores."""

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlmodel import Session, col, select

from resume_tailor_harness.services import application_events
from resume_tailor_harness.tracking.repository import application_for_job, has_progress
from resume_tailor_harness.tracking.tables import (
    ApplicationQuestion,
    CoverLetter,
    Job,
    ResumeVersion,
)
from resume_tailor_harness.workspace_agent.tables import WorkspaceNote


def revision(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()


def record(value: Any) -> dict:
    return value.model_dump(mode="json") if value is not None else {}


def job_snapshot(session: Session, job_id: int) -> dict:
    job = session.get(Job, job_id)
    if job is None:
        raise ValueError("Unknown job")
    return {
        "job": record(job),
        "application": record(application_for_job(session, job_id)),
        "events": [
            record(row) for row in application_events.list_events(session, job_id)
        ],
        "notes": [
            record(row)
            for row in session.exec(
                select(WorkspaceNote).where(WorkspaceNote.job_id == job_id)
            ).all()
        ],
        "resumes": [
            record(row)
            for row in session.exec(
                select(ResumeVersion).where(ResumeVersion.job_id == job_id)
            ).all()
        ],
        "cover_letters": [
            record(row)
            for row in session.exec(
                select(CoverLetter).where(CoverLetter.job_id == job_id)
            ).all()
        ],
        "questions": [
            record(row)
            for row in session.exec(
                select(ApplicationQuestion).where(ApplicationQuestion.job_id == job_id)
            ).all()
        ],
        "has_progress": has_progress(session, job_id),
    }


def find_jobs(
    session: Session, query: str = "", offset: int = 0, limit: int = 20
) -> dict:
    if len(query) > 200:
        raise ValueError("Query is too long")
    statement = select(Job)
    if query.strip():
        # Escape SQL wildcards so the query is a literal search, not a pattern.
        needle = (
            "%"
            + query.strip()
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
            + "%"
        )
        statement = statement.where(
            col(Job.title).ilike(needle, escape="\\")
            | col(Job.company).ilike(needle, escape="\\")
        )
    start, count = max(0, offset), max(1, min(limit, 30))
    rows = session.exec(
        statement.order_by(col(Job.id)).offset(start).limit(count + 1)
    ).all()
    fields = {"id", "company", "title", "location", "url", "status", "archived_at"}
    return {
        "records": [
            {k: v for k, v in record(row).items() if k in fields}
            for row in rows[:count]
        ],
        "next_offset": start + count if len(rows) > count else None,
    }


def public_job_context(
    session: Session,
    job_id: int,
    section: str = "overview",
    offset: int = 0,
    record_id: int | None = None,
) -> dict:
    snapshot = job_snapshot(session, job_id)
    result: dict = {
        "job_id": job_id,
        "revision": revision(snapshot),
        "section": section,
    }
    if record_id is not None:
        if section not in {"events", "notes", "resumes", "cover_letters", "questions"}:
            raise ValueError("Choose a record section")
        row = next((row for row in snapshot[section] if row["id"] == record_id), None)
        if row is None:
            raise ValueError("Record does not belong to this job")
        text = json.dumps(row, ensure_ascii=False)
        start = max(0, offset)
        return {
            **result,
            "record_id": record_id,
            "text": text[start : start + 16000],
            "next_offset": start + 16000 if start + 16000 < len(text) else None,
        }
    if section == "overview":
        job = snapshot["job"]
        text = job.pop("jd_text", "")
        result.update(
            job=job,
            description=text[:16000],
            description_truncated=len(text) > 16000,
            application=snapshot["application"],
            has_progress=snapshot["has_progress"],
            sections=[
                "description",
                "events",
                "notes",
                "resumes",
                "cover_letters",
                "questions",
                "preparation",
            ],
        )
    elif section == "description":
        text = snapshot["job"]["jd_text"]
        start = max(0, offset)
        result.update(
            text=text[start : start + 16000],
            next_offset=start + 16000 if start + 16000 < len(text) else None,
        )
    elif section == "preparation":
        from resume_tailor_harness.services.role_preparation import (
            load_role_preparation_brief,
        )
        from resume_tailor_harness.services.company_intelligence import (
            load_company_intelligence,
        )

        result["brief"] = record(load_role_preparation_brief(session, job_id))
        result["company_research"] = record(
            load_company_intelligence(session, snapshot["job"].get("company"))
        )
        result["saved_preparation_ids"] = [
            row["id"]
            for row in snapshot["notes"]
            if row["kind"] == "preparation" and not row["deleted"]
        ]
    elif section in {"events", "notes", "resumes", "cover_letters", "questions"}:
        rows = snapshot[section]
        start = max(0, offset)
        page, size = [], 0
        for row in rows[start : start + 20]:
            rendered = json.dumps(row, ensure_ascii=False)
            if size + len(rendered) > 40000:
                if not page:
                    page.append(
                        {
                            "id": row["id"],
                            "truncated": True,
                            "preview": rendered[:12000],
                        }
                    )
                break
            page.append(row)
            size += len(rendered)
        result.update(
            records=page,
            total=len(rows),
            next_offset=start + len(page) if start + len(page) < len(rows) else None,
        )
    else:
        raise ValueError("Unknown workspace section")
    return result


def search_history(root: Path, query: str, offset: int = 0, limit: int = 10) -> dict:
    if not query.strip() or len(query) > 200:
        raise ValueError("Supply a search query of 1–200 characters")
    # Kind stores own paths and archived/corrupt-file handling. Never accept a path.
    from resume_tailor_harness.career_lab.store import list_sessions as lab_sessions
    from resume_tailor_harness.interview.store import (
        list_sessions as interview_sessions,
    )
    from resume_tailor_harness.profile.coach_store import (
        list_sessions as coach_sessions,
    )
    from resume_tailor_harness.discovery.scout_store import (
        list_sessions as scout_sessions,
    )

    readers = [
        (
            "career-lab",
            lambda: lab_sessions(root / "career-lab", include_archived=True),
        ),
        (
            "interview",
            lambda: interview_sessions(root / "interview", include_archived=True),
        ),
        ("coach", lambda: coach_sessions(root / "profile", include_archived=True)),
        ("scout", lambda: scout_sessions(root, include_archived=True)),
    ]
    matches = []
    for surface, reader in readers:
        for item in reader():
            for index, turn in enumerate(item.get("turns", [])):
                text = str(turn.get("text", ""))
                if query.casefold() in text.casefold():
                    at = text.casefold().find(query.casefold())
                    matches.append(
                        {
                            "surface": surface,
                            "session_id": item["session_id"],
                            "turn": index,
                            "role": turn.get("role"),
                            "excerpt": text[max(0, at - 200) : at + 1800],
                            "job_id": item.get("job_id"),
                            "historical_not_verified_fact": True,
                        }
                    )
    start, count = max(0, offset), max(1, min(limit, 20))
    return {
        "records": matches[start : start + count],
        "total": len(matches),
        "next_offset": start + count if start + count < len(matches) else None,
    }
