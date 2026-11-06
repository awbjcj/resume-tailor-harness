import json
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from resume_tailor_harness.config import Settings
from resume_tailor_harness.db import make_engine
from resume_tailor_harness.models.resume import ResumeContent
from resume_tailor_harness.models.evidence_portfolio import EvidencePortfolio
from resume_tailor_harness.models.profile import Contact
from resume_tailor_harness.render.export import job_dir, resume_pdf_name
from resume_tailor_harness.render.render_config import RenderConfig
from resume_tailor_harness.render.service import render_version
from resume_tailor_harness.services.board import delete_resume_versions
from resume_tailor_harness.tenancy.context import UserContext, use_context
from resume_tailor_harness.tenancy.workspace import WorkspacePaths
from resume_tailor_harness.tracking.repository import (
    application_for_job,
    get_resume_version,
    save_application,
    save_job,
    save_resume_version,
)
from resume_tailor_harness.tracking.tables import Application, Job, JobStatus, ResumeVersion


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _require_id(value: int | None) -> int:
    assert value is not None
    return value


def test_render_version_sets_path_and_marks_rendered(tmp_path):
    calls = {}

    def fake_render(content, output_path, template_path, *, fit_pages=None):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"%PDF-fake")
        calls["content"] = content
        calls["template_path"] = template_path
        calls["fit_pages"] = fit_pages
        return Path(output_path)

    config = RenderConfig(
        template_path="templates/resume.typ", output_dir=str(tmp_path / "out")
    )
    with _session() as s:
        job = save_job(
            s,
            Job(
                source="manual",
                jd_text="jd",
                company="Acme",
                title="Engineer",
                status=JobStatus.tailored.value,
            ),
        )
        version = save_resume_version(
            s,
            ResumeVersion(
                job_id=_require_id(job.id),
                round=1,
                content_json=ResumeContent(contact=Contact(name="Ada")).model_dump(
                    mode="json"
                ),
            ),
        )

        path = render_version(s, _require_id(version.id), config, render_fn=fake_render)

        assert path is not None
        assert path.exists()
        assert path.suffix == ".pdf"
        assert isinstance(calls["content"], ResumeContent)
        assert calls["fit_pages"] == 1
        refreshed = get_resume_version(s, _require_id(version.id))
        assert refreshed is not None
        assert refreshed.pdf_path == str(path)
        assert job.status == JobStatus.rendered.value


def test_render_version_passes_frozen_portfolio_highlight_terms(tmp_path):
    calls = {}

    def fake_render(
        content, output_path, template_path, *, fit_pages=None, highlight_terms=None
    ):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"%PDF-fake")
        calls["highlight_terms"] = highlight_terms
        return Path(output_path)

    config = RenderConfig(
        template_path="templates/resume.typ", output_dir=str(tmp_path / "out")
    )
    with _session() as session:
        job = save_job(session, Job(source="manual", jd_text="jd"))
        portfolio = EvidencePortfolio(status="planned", highlight_terms=["Python"])
        version = save_resume_version(
            session,
            ResumeVersion(
                job_id=_require_id(job.id),
                round=1,
                content_json=ResumeContent(contact=Contact(name="Ada")).model_dump(
                    mode="json"
                ),
                evidence_portfolio_json=portfolio.model_dump(mode="json"),
                evidence_portfolio_status="planned",
            ),
        )

        render_version(session, _require_id(version.id), config, render_fn=fake_render)

    assert calls["highlight_terms"] == ["Python"]


def test_multi_user_render_forces_output_root_and_rejects_legacy_template(tmp_path):
    workspace = WorkspacePaths(tmp_path / "users" / "alice")
    workspace.output_dir.mkdir(parents=True)
    context = UserContext(
        user_id="alice0000000",
        username="alice",
        role="user",
        paths=workspace,
        settings=Settings(_env_file=None),  # type: ignore[call-arg]
        engine=None,
        system_engine=None,
        own_key_providers=frozenset(),
    )
    outside = tmp_path / "outside"
    config = RenderConfig(
        template_path=str(tmp_path / "untrusted.typ"),
        output_dir=str(outside),
    )
    with _session() as session:
        job = save_job(session, Job(source="manual", jd_text="jd"))
        version = save_resume_version(
            session,
            ResumeVersion(
                job_id=_require_id(job.id),
                content_json=ResumeContent(contact=Contact(name="Ada")).model_dump(
                    mode="json"
                ),
            ),
        )
        with use_context(context), pytest.raises(ValueError, match="template paths"):
            render_version(
                session,
                _require_id(version.id),
                config,
                render_fn=lambda *_args, **_kwargs: outside / "not-used.pdf",
            )

        def fake_render(_content, output_path, _template_path, **_kwargs):
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"%PDF")
            return path

        with use_context(context):
            rendered = render_version(
                session,
                _require_id(version.id),
                RenderConfig(template="classic", output_dir=str(outside)),
                render_fn=fake_render,
            )
        assert rendered is not None
        assert rendered.is_relative_to(workspace.output_dir)
    assert not outside.exists()


def test_render_version_uses_distinct_paths_for_versions_same_job_same_day(tmp_path):
    def fake_render(content, output_path, template_path, *, fit_pages=None):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"%PDF-fake")
        return Path(output_path)

    config = RenderConfig(
        template_path="templates/resume.typ", output_dir=str(tmp_path / "out")
    )
    with _session() as s:
        job = save_job(
            s,
            Job(
                source="manual",
                jd_text="jd",
                company="Acme",
                title="Engineer",
                status=JobStatus.tailored.value,
            ),
        )
        first = save_resume_version(
            s,
            ResumeVersion(
                job_id=_require_id(job.id),
                round=1,
                content_json=ResumeContent(contact=Contact(name="Ada")).model_dump(
                    mode="json"
                ),
            ),
        )
        second = save_resume_version(
            s,
            ResumeVersion(
                job_id=_require_id(job.id),
                round=2,
                content_json=ResumeContent(contact=Contact(name="Ada")).model_dump(
                    mode="json"
                ),
            ),
        )

        first_path = render_version(
            s, _require_id(first.id), config, render_fn=fake_render
        )
        second_path = render_version(
            s, _require_id(second.id), config, render_fn=fake_render
        )

        assert first_path is not None
        assert second_path is not None
        assert first_path != second_path
        assert f"v{_require_id(first.id)}" in first_path.stem
        assert f"v{_require_id(second.id)}" in second_path.stem


def test_render_version_missing_returns_none(tmp_path):
    config = RenderConfig(output_dir=str(tmp_path))

    def fake_render(content, output_path, template_path, *, fit_pages=None):
        return Path(output_path)

    with _session() as s:
        assert render_version(s, 4242, config, render_fn=fake_render) is None


def test_render_version_can_disable_one_page_fit(tmp_path):
    calls = {}

    def fake_render(content, output_path, template_path, *, fit_pages=None):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"%PDF-fake")
        calls["fit_pages"] = fit_pages
        return Path(output_path)

    config = RenderConfig(
        template="classic",
        fit_one_page=False,
        output_dir=str(tmp_path / "out"),
    )
    with _session() as session:
        job = save_job(
            session,
            Job(source="manual", jd_text="jd", company="Acme", title="Engineer"),
        )
        version = save_resume_version(
            session,
            ResumeVersion(
                job_id=_require_id(job.id),
                round=1,
                content_json=ResumeContent(contact=Contact(name="Ada")).model_dump(
                    mode="json"
                ),
            ),
        )
        render_version(session, _require_id(version.id), config, render_fn=fake_render)
    assert calls["fit_pages"] == 2


def test_deleting_during_compilation_does_not_recreate_the_pdf(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'workspace.db').as_posix()}")
    SQLModel.metadata.create_all(engine)
    config = RenderConfig(template="classic", output_dir=str(tmp_path / "output"))
    with Session(engine) as session:
        job = save_job(session, Job(source="manual"))
        version = save_resume_version(
            session,
            ResumeVersion(
                job_id=_require_id(job.id),
                content_json=ResumeContent(contact=Contact(name="Ada")).model_dump(
                    mode="json"
                ),
            ),
        )
        version_id = _require_id(version.id)

        def render_then_delete(_content, output_path, _template_path, **_kwargs):
            output_path.write_bytes(b"%PDF-staged")
            with Session(engine) as deleting:
                assert delete_resume_versions(deleting, [version_id]).deleted == 1
            return output_path

        assert (
            render_version(session, version_id, config, render_fn=render_then_delete)
            is None
        )
        assert not list((tmp_path / "output").rglob("*.pdf"))
    engine.dispose()


def test_rendering_does_not_overwrite_the_pdf_a_version_filename_links_to(tmp_path):
    workspace = WorkspacePaths(tmp_path / "alice")
    context = UserContext(
        user_id="alice0000000",
        username="alice",
        role="user",
        paths=workspace,
        settings=Settings(_env_file=None),  # type: ignore[call-arg]
        engine=None,
        system_engine=None,
        own_key_providers=frozenset(),
    )
    config = RenderConfig(template="classic")

    def fake_render(_content, output_path, _template_path, **_kwargs):
        output_path.write_bytes(b"%PDF-new")
        return output_path

    with _session() as session, use_context(context):
        job = save_job(session, Job(source="manual"))
        version = save_resume_version(
            session,
            ResumeVersion(
                job_id=_require_id(job.id),
                content_json=ResumeContent(contact=Contact(name="Ada")).model_dump(
                    mode="json"
                ),
            ),
        )
        directory = job_dir(workspace.output_dir, job)
        directory.mkdir(parents=True)
        other_pdf = directory / "retained.pdf"
        other_pdf.write_bytes(b"%PDF-retained")
        output = directory / resume_pdf_name(version)
        output.symlink_to(other_pdf)

        path = render_version(
            session, _require_id(version.id), config, render_fn=fake_render
        )

        assert path == output and not output.is_symlink()
        assert output.read_bytes() == b"%PDF-new"
        assert other_pdf.read_bytes() == b"%PDF-retained"


def test_style_change_isolates_pdf_shared_with_selected_version(tmp_path):
    context = UserContext(
        user_id="alice0000000",
        username="alice",
        role="user",
        paths=WorkspacePaths(tmp_path),
        settings=Settings(_env_file=None),  # type: ignore[call-arg]
        engine=None,
        system_engine=None,
        own_key_providers=frozenset(),
    )

    def fake_render(_content, output_path, template_path, **_kwargs):
        output_path.write_bytes(template_path.stem.encode())
        return output_path

    with use_context(context), _session() as session:
        job_id = _require_id(save_job(session, Job(source="manual")).id)
        version = save_resume_version(
            session,
            ResumeVersion(
                job_id=job_id,
                content_json=ResumeContent(contact=Contact(name="Ada")).model_dump(mode="json"),
            ),
        )
        version_id = _require_id(version.id)
        shared = render_version(session, version_id, RenderConfig(template="classic"), fake_render)
        assert shared is not None
        classic = shared.read_bytes()
        selected = save_resume_version(
            session,
            ResumeVersion(
                job_id=job_id,
                pdf_path=shared.relative_to(tmp_path).as_posix(),
                pdf_template_id="classic",
            ),
        )
        selected_id = _require_id(selected.id)
        save_application(session, Application(job_id=job_id, resume_version_id=selected_id))

        path = render_version(session, version_id, RenderConfig(template="modern"), fake_render)

        assert path is not None and path != shared
        assert path.read_bytes() != classic
        assert version.pdf_path == str(path)
        assert version.pdf_template_id == "modern"
        assert shared.read_bytes() == classic
        assert selected.pdf_template_id == "classic"
        application = application_for_job(session, job_id)
        assert application is not None and application.resume_version_id == selected_id
        manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))
        assert [entry["file"] for entry in manifest["resumeVersions"]] == [path.name, shared.name]

        assert render_version(
            session, version_id, RenderConfig(template="technical"), fake_render
        ) == path
        assert shared.read_bytes() == classic
        assert set(path.parent.glob("*.pdf")) == {path, shared}


def test_render_commit_failure_restores_the_previous_pdf(monkeypatch, tmp_path):
    def fake_render(_content, output_path, template_path, **_kwargs):
        output_path.write_bytes(template_path.name.encode())
        return output_path

    config = RenderConfig(template="classic", output_dir=str(tmp_path / "output"))
    with _session() as session:
        job = save_job(session, Job(source="manual"))
        version = save_resume_version(
            session,
            ResumeVersion(
                job_id=_require_id(job.id),
                content_json=ResumeContent(contact=Contact(name="Ada")).model_dump(
                    mode="json"
                ),
            ),
        )
        version_id = _require_id(version.id)
        path = render_version(session, version_id, config, render_fn=fake_render)
        assert path is not None
        original = path.read_bytes()

        def fail_commit():
            raise RuntimeError("commit failed")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="commit failed"):
            render_version(
                session,
                version_id,
                config.model_copy(update={"template": "modern"}),
                render_fn=fake_render,
            )

        assert path.read_bytes() == original
        assert version.pdf_template_id == "classic"


class _FakeConfigStore:
    """Minimal store honoring the get/put contract clear_custom_render_template needs."""

    def __init__(self, doc: RenderConfig) -> None:
        self.doc = doc

    def get(self, key: str) -> RenderConfig:
        assert key == "render"
        return self.doc

    def put(self, key: str, doc: RenderConfig) -> None:
        assert key == "render"
        self.doc = doc


def test_clear_custom_render_template_falls_back_to_classic():
    from resume_tailor_harness.services.render_templates import (
        clear_custom_render_template,
    )

    store = _FakeConfigStore(RenderConfig(template="custom:mine"))
    clear_custom_render_template(store)
    assert store.doc.template == "classic"


def test_clear_custom_render_template_leaves_bundled_and_empty_alone():
    from resume_tailor_harness.services.render_templates import (
        clear_custom_render_template,
    )

    for template in ("classic", None):
        store = _FakeConfigStore(RenderConfig(template=template))
        clear_custom_render_template(store)
        assert store.doc.template == template
