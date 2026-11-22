import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from sqlmodel import Session

from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.config import Settings
from resume_tailor_harness.render import export
from resume_tailor_harness.render.export import (
    build_manifest,
    cover_letter_download_name,
    cover_letter_pdf_name,
    export_job_artifacts,
    job_dir,
    job_slug,
    resume_download_name,
    resume_json_name,
    resume_pdf_name,
)
from resume_tailor_harness.tracking.repository import (
    save_application,
    save_cover_letter,
    save_job,
    save_resume_version,
)
from resume_tailor_harness.tracking.tables import (
    Application,
    CoverLetter,
    Job,
    ResumeVersion,
)
from resume_tailor_harness.tenancy.context import UserContext, use_context
from resume_tailor_harness.tenancy.storage import TenantPathError
from resume_tailor_harness.tenancy.workspace import WorkspacePaths


def test_job_slug_and_version_filenames():
    job = Job(id=42, source="manual", company="Acme Corp", title="Senior Engineer")
    version = ResumeVersion(id=7, job_id=42, round=1, origin="revision")
    cover = CoverLetter(id=3, job_id=42, origin="draft")

    assert job_slug(job) == "acme_corp-senior_engineer-42"
    assert job_dir("output", job) == Path("output") / "acme_corp-senior_engineer-42"
    assert resume_pdf_name(version) == "resume-v7-revision.pdf"
    assert resume_json_name(version) == "resume-v7-revision.content.json"
    assert cover_letter_pdf_name(cover) == "cover-letter-v3-draft.pdf"


def test_export_manifest_uses_manual_application_link():
    job = Job(
        id=42, source="manual", url="https://posting.example/jobs/42",
        criteria_json={"manual_details": {"application_url": "https://apply.example/42"}},
    )
    assert build_manifest(job, [], [], None)["job"]["url"] == "https://apply.example/42"


def test_resume_download_name_uses_company_and_title():
    job = Job(id=42, source="manual", company="Acme Corp", title="Senior Engineer")
    version = ResumeVersion(id=7, job_id=42, round=1, origin="revision")

    assert (
        resume_download_name(job, version) == "Acme_Corp-Senior_Engineer-Resume-v7.pdf"
    )


def test_cover_letter_download_name_uses_company_and_title():
    job = Job(id=42, source="manual", company="Acme Corp", title="Senior Engineer")
    cover = CoverLetter(id=3, job_id=42, origin="draft")

    assert (
        cover_letter_download_name(job, cover)
        == "Acme_Corp-Senior_Engineer-CoverLetter-v3.pdf"
    )


def test_download_name_falls_back_when_company_or_title_missing():
    job = Job(id=42, source="manual", company=None, title="")
    version = ResumeVersion(id=7, job_id=42, round=1, origin="tailor")

    assert resume_download_name(job, version) == "Company-Role-Resume-v7.pdf"


def test_download_name_strips_special_characters_and_collapses_whitespace():
    job = Job(
        id=42,
        source="manual",
        company="Acme, Inc.  (Remote)",
        title="C++  Engineer -- Backend",
    )
    version = ResumeVersion(id=9, job_id=42, round=1, origin="tailor")

    assert (
        resume_download_name(job, version)
        == "Acme_Inc_Remote-C_Engineer_Backend-Resume-v9.pdf"
    )


def test_job_dir_rebases_default_output_into_active_workspace(tmp_path):
    paths = WorkspacePaths(tmp_path / "users" / "alice")
    context = UserContext(
        user_id="abc123def456",
        username="alice",
        role="user",
        paths=paths,
        settings=Settings(_env_file=None),  # type: ignore[call-arg]
        engine=None,
        system_engine=None,
        own_key_providers=frozenset(),
    )
    job = Job(id=42, source="manual", company="Acme", title="Engineer")

    with use_context(context):
        assert job_dir("output", job).is_relative_to(paths.output_dir)


def test_build_manifest_shape():
    job = Job(id=42, source="manual", company="Acme", title="Eng")
    version = ResumeVersion(
        id=7,
        job_id=42,
        round=1,
        origin="revision",
        instruction="be concise",
        parent_version_id=5,
        fact_check_passed=True,
    )
    cover = CoverLetter(id=3, job_id=42, origin="draft", fact_check_passed=True)
    app = Application(id=1, job_id=42, resume_version_id=7, cover_letter_id=3)

    manifest = build_manifest(job, [version], [cover], app)

    assert manifest["job"]["id"] == 42
    assert manifest["resumeVersions"][0]["instruction"] == "be concise"
    assert manifest["resumeVersions"][0]["file"] == "resume-v7-revision.pdf"
    assert manifest["applied"] == {"resumeVersionId": 7, "coverLetterId": 3}


def test_export_writes_manifest_and_content_idempotently(tmp_path):
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        job = save_job(session, Job(source="manual", company="Acme", title="Eng"))
        assert job.id is not None
        version = save_resume_version(
            session,
            ResumeVersion(
                job_id=job.id,
                round=1,
                origin="tailor",
                content_json={"contact": {"name": "Ada"}},
                fact_check_passed=True,
            ),
        )
        cover = save_cover_letter(
            session,
            CoverLetter(
                job_id=job.id,
                origin="draft",
                content_json={"contact": {"name": "Ada"}},
                fact_check_passed=True,
            ),
        )
        save_application(
            session,
            Application(
                job_id=job.id, resume_version_id=version.id, cover_letter_id=cover.id
            ),
        )

        out = export_job_artifacts(session, job.id, base=tmp_path)
        assert out is not None
        first_manifest = (out / "manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(first_manifest)

        assert manifest["resumeVersions"][0]["id"] == version.id
        assert manifest["coverLetters"][0]["id"] == cover.id
        assert (out / f"resume-v{version.id}-tailor.content.json").exists()
        assert (out / f"cover-letter-v{cover.id}-draft.content.json").exists()

        export_job_artifacts(session, job.id, base=tmp_path)
        assert (out / "manifest.json").read_text(encoding="utf-8") == first_manifest


def test_export_reserves_the_writer_until_sidecars_are_published(tmp_path, monkeypatch):
    database = tmp_path / "workspace.db"
    engine = make_engine(f"sqlite:///{database.as_posix()}")
    init_db(engine)
    with Session(engine) as session:
        job_id = save_job(session, Job(source="manual")).id
        assert job_id is not None
        save_resume_version(session, ResumeVersion(job_id=job_id))

    writing, release = Event(), Event()
    write_json = export._write_json

    def paused_write(path, value):
        if path.name.endswith(".content.json"):
            writing.set()
            assert release.wait(5)
        write_json(path, value)

    def publish():
        with Session(engine) as session:
            return export_job_artifacts(session, job_id, base=tmp_path / "output")

    monkeypatch.setattr(export, "_write_json", paused_write)
    with ThreadPoolExecutor(max_workers=1) as worker:
        pending = worker.submit(publish)
        try:
            assert writing.wait(5)
            with sqlite3.connect(database, timeout=0.1) as writer:
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    writer.execute("BEGIN IMMEDIATE")
        finally:
            release.set()
        assert pending.result(5) is not None
    engine.dispose()


def test_export_refuses_a_job_directory_link_outside_the_workspace(tmp_path):
    paths = WorkspacePaths(tmp_path / "alice")
    paths.output_dir.mkdir(parents=True)
    context = UserContext(
        user_id="alice0000000",
        username="alice",
        role="user",
        paths=paths,
        settings=Settings(_env_file=None),  # type: ignore[call-arg]
        engine=None,
        system_engine=None,
        own_key_providers=frozenset(),
    )
    outside = tmp_path / "other-workspace"
    outside.mkdir()
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session, use_context(context):
        job = save_job(session, Job(source="manual"))
        assert job.id is not None
        job_dir("output", job).symlink_to(outside, target_is_directory=True)

        with pytest.raises(TenantPathError):
            export_job_artifacts(session, job.id)

    assert list(outside.iterdir()) == []
    engine.dispose()
