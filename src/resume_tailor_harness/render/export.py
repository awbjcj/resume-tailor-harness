"""Filesystem projection of a job's resume and cover-letter versions."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlmodel import Session

from resume_tailor_harness.db import workspace_write
from resume_tailor_harness.progress import atomic_write_text
from resume_tailor_harness.render.renderer import _slug
from resume_tailor_harness.tenancy.paths import resolve_tenant_path
from resume_tailor_harness.tenancy.storage import TenantPathError, artifact_path
from resume_tailor_harness.tracking.repository import (
    application_for_job,
    cover_letters_for_job,
    get_job,
    resume_versions_for_job,
)
from resume_tailor_harness.tracking.tables import (
    Application,
    CoverLetter,
    Job,
    ResumeVersion,
)


def job_slug(job: Job) -> str:
    company = _slug(job.company or "") or "company"
    title = _slug(job.title or "") or "role"
    return f"{company}-{title}-{job.id}"


def job_dir(base: str | Path, job: Job) -> Path:
    return resolve_tenant_path(base) / job_slug(job)


def _origin(value: str | None, fallback: str) -> str:
    return _slug(value or "") or fallback


def _friendly_part(text: str, fallback: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text or "", flags=re.UNICODE).strip()
    cleaned = re.sub(r"[\s-]+", "_", cleaned).strip("_")
    return cleaned or fallback


def resume_download_name(job: Job, version: ResumeVersion) -> str:
    company = _friendly_part(job.company or "", "Company")
    title = _friendly_part(job.title or "", "Role")
    return f"{company}-{title}-Resume-v{version.id}.pdf"


def cover_letter_download_name(job: Job, cover_letter: CoverLetter) -> str:
    company = _friendly_part(job.company or "", "Company")
    title = _friendly_part(job.title or "", "Role")
    return f"{company}-{title}-CoverLetter-v{cover_letter.id}.pdf"


def resume_pdf_name(version: ResumeVersion) -> str:
    return f"resume-v{version.id}-{_origin(version.origin, 'tailor')}.pdf"


def resume_json_name(version: ResumeVersion) -> str:
    return f"resume-v{version.id}-{_origin(version.origin, 'tailor')}.content.json"


def cover_letter_pdf_name(cover_letter: CoverLetter) -> str:
    return (
        f"cover-letter-v{cover_letter.id}-{_origin(cover_letter.origin, 'draft')}.pdf"
    )


def cover_letter_json_name(cover_letter: CoverLetter) -> str:
    return f"cover-letter-v{cover_letter.id}-{_origin(cover_letter.origin, 'draft')}.content.json"


def _version_entry(version: ResumeVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "round": version.round,
        "origin": version.origin,
        "instruction": version.instruction,
        "parentVersionId": version.parent_version_id,
        "factCheckPassed": version.fact_lock_passed,
        "reviewScore": version.review_score,
        "createdAt": version.created_at.isoformat() if version.created_at else None,
        "file": (
            Path(version.pdf_path).name if version.pdf_path else resume_pdf_name(version)
        ),
        "pdfTemplateId": version.pdf_template_id,
        "contentFile": resume_json_name(version),
    }


def _cover_letter_entry(cover_letter: CoverLetter) -> dict[str, Any]:
    return {
        "id": cover_letter.id,
        "origin": cover_letter.origin,
        "instruction": cover_letter.instruction,
        "parentId": cover_letter.parent_id,
        "factCheckPassed": cover_letter.fact_check_passed,
        "createdAt": cover_letter.created_at.isoformat()
        if cover_letter.created_at
        else None,
        "file": cover_letter_pdf_name(cover_letter),
        "contentFile": cover_letter_json_name(cover_letter),
    }


def build_manifest(
    job: Job,
    versions: list[ResumeVersion],
    cover_letters: list[CoverLetter],
    application: Application | None,
) -> dict[str, Any]:
    return {
        "job": {
            "id": job.id,
            "company": job.company,
            "title": job.title,
            "url": job.url,
            "status": job.status,
        },
        "resumeVersions": [_version_entry(v) for v in sorted(versions, key=_row_id)],
        "coverLetters": [
            _cover_letter_entry(cl) for cl in sorted(cover_letters, key=_row_id)
        ],
        "applied": {
            "resumeVersionId": application.resume_version_id if application else None,
            "coverLetterId": application.cover_letter_id if application else None,
        },
    }


def _row_id(row: ResumeVersion | CoverLetter) -> int:
    return row.id or 0


def _write_json(path: Path, value: Any) -> None:
    if path.is_symlink():
        raise TenantPathError("export file is a symbolic link")
    atomic_write_text(
        path, json.dumps(value, indent=2, sort_keys=True), root=path.parent
    )


def _prune_previous_exports(
    root: Path, current: Path, job_id: int, removed: set[str]
) -> None:
    # Company and title can change after a re-pull. Both slugs omit hyphens,
    # so the last part of a generated directory name is always the job ID.
    name_pattern = re.compile(rf"[a-z0-9_]+-[a-z0-9_]+-{job_id}")
    for directory in root.glob(f"*-{job_id}"):
        if (
            directory == current
            or not name_pattern.fullmatch(directory.name)
            or directory.is_symlink()
            or directory.is_junction()
            or not directory.is_dir()
        ):
            continue
        manifest_path = directory / "manifest.json"
        if manifest_path.is_symlink():
            continue
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise OSError(f"could not read export manifest for job {job_id}") from exc
            job = manifest.get("job") if isinstance(manifest, dict) else None
            if not isinstance(job, dict) or job.get("id") != job_id:
                continue
            versions = manifest.get("resumeVersions", [])
            if isinstance(versions, list):
                kept = []
                removed_ids = []
                for entry in versions:
                    filename = entry.get("contentFile") if isinstance(entry, dict) else None
                    if isinstance(filename, str) and filename in removed:
                        removed_ids.append(entry.get("id"))
                    else:
                        kept.append(entry)
                if removed_ids:
                    manifest["resumeVersions"] = kept
                    applied = manifest.get("applied")
                    if (
                        isinstance(applied, dict)
                        and applied.get("resumeVersionId") in removed_ids
                    ):
                        applied["resumeVersionId"] = None
                    _write_json(manifest_path, manifest)
        for filename in removed:
            (directory / filename).unlink(missing_ok=True)


def export_job_artifacts(
    session: Session,
    job_id: int,
    base: str | Path = "output",
    *,
    removed_resume_sidecars: Sequence[str] = (),
    existing_only: bool = False,
) -> Path | None:
    # Callers export committed rows. Serialize the snapshot and file writes so
    # an older export cannot restore a version removed by a newer operation.
    with workspace_write(session):
        session.expire_all()
        job = get_job(session, job_id)
        if job is None:
            return None

        versions = sorted(resume_versions_for_job(session, job_id), key=_row_id)
        cover_letters = sorted(cover_letters_for_job(session, job_id), key=_row_id)
        application = application_for_job(session, job_id)

        root = artifact_path(resolve_tenant_path(base))
        out = artifact_path(root / job_slug(job))
        removed = set(removed_resume_sidecars) - {resume_json_name(v) for v in versions}
        if removed:
            if any(Path(name).name != name for name in removed):
                raise TenantPathError("invalid export filename")
            _prune_previous_exports(root, out, job_id, removed)
            for name in removed:
                (out / name).unlink(missing_ok=True)
        if existing_only and not (out / "manifest.json").is_file():
            return None
        out.mkdir(parents=True, exist_ok=True)

        for version in versions:
            _write_json(out / resume_json_name(version), version.content_json or {})
        for cover_letter in cover_letters:
            _write_json(
                out / cover_letter_json_name(cover_letter),
                cover_letter.content_json or {},
            )
        _write_json(
            out / "manifest.json",
            build_manifest(job, versions, cover_letters, application),
        )
        return out
