import logging
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from typing import Callable
from uuid import uuid4

from sqlmodel import Session

from resume_tailor_harness.db import workspace_write
from resume_tailor_harness.models.evidence_portfolio import EvidencePortfolio
from resume_tailor_harness.models.resume import ResumeContent
from resume_tailor_harness.render.export import (
    export_job_artifacts,
    job_dir,
    resume_pdf_name,
)
from resume_tailor_harness.render.render_config import RenderConfig
from resume_tailor_harness.render.renderer import render_pdf
from resume_tailor_harness.render.templates import BUNDLED, template_path_for
from resume_tailor_harness.tenancy.context import current_context
from resume_tailor_harness.tenancy.paths import resolve_tenant_path
from resume_tailor_harness.tenancy.storage import (
    TenantPathError,
    artifact_path,
    artifact_pdf_identity,
)
from resume_tailor_harness.tracking.repository import (
    get_job,
    get_resume_version,
    referenced_pdf_paths,
)
from resume_tailor_harness.tracking.stages import advance
from resume_tailor_harness.tracking.tables import Job, JobStatus, ResumeVersion

RenderFn = Callable[..., Path]
logger = logging.getLogger(__name__)


def render_version(
    session: Session,
    version_id: int,
    config: RenderConfig,
    render_fn: RenderFn = render_pdf,
) -> Path | None:
    """Render one resume version to PDF, store its path, mark the job rendered."""
    version: ResumeVersion | None = get_resume_version(session, version_id)
    if version is None:
        return None
    job_id = version.job_id
    created_at = version.created_at
    job = get_job(session, job_id)

    content = ResumeContent.model_validate(version.content_json or {})
    context = current_context()
    output_base: str | Path = (
        context.paths.output_dir if context is not None else config.output_dir
    )
    out_dir = (
        job_dir(output_base, job)
        if job is not None
        else resolve_tenant_path(output_base)
    )
    # Confine the directory. Replacing the named file must not follow a link
    # at that filename to another version's PDF.
    out_path = artifact_path(out_dir) / resume_pdf_name(version)
    template_path = template_path_for(config)
    resolved_template = template_path.resolve()
    template_id = config.template or next(
        (item.id for item in BUNDLED.values() if item.path == resolved_template), None
    )

    render_kwargs: dict[str, int | list[str] | None] = {
        "fit_pages": 1 if config.fit_one_page else 2
    }
    if version.evidence_portfolio_json is not None:
        portfolio = EvidencePortfolio.model_validate(version.evidence_portfolio_json)
        render_kwargs["highlight_terms"] = portfolio.highlight_terms
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".resume-render-", dir=out_path.parent) as staging:
        staged = Path(staging) / out_path.name
        render_fn(content, staged, template_path, **render_kwargs)
        # Compilation can take seconds. Hold the writer only during publication
        # and check that deletion did not win while the PDF was compiling.
        with workspace_write(session):
            version = session.get(ResumeVersion, version_id, populate_existing=True)
            if (
                version is None
                or version.job_id != job_id
                or version.created_at != created_at
            ):
                return None
            # Imported versions can point at the same PDF. Keep a private
            # filename once allocated so later style changes reuse it.
            private_prefix = f"{out_path.stem}-render-"
            existing = artifact_pdf_identity(version.pdf_path)
            if (
                existing is not None
                and existing.parent == out_path.parent.resolve()
                and existing.name.startswith(private_prefix)
                and existing.suffix == ".pdf"
            ):
                out_path = existing
            destination = artifact_pdf_identity(out_path)
            if destination is None or referenced_pdf_paths(
                session, [destination], exclude_resume_ids=[version_id]
            ):
                out_path = out_path.with_name(f"{private_prefix}{uuid4().hex}.pdf")
            version.pdf_path = str(out_path)
            version.pdf_file_key = out_path.name.casefold()
            version.pdf_template_id = template_id
            job = session.get(Job, job_id, populate_existing=True)
            if job is not None:
                advance(job, JobStatus.rendered.value, never_regress=True)
            previous = Path(staging) / "previous.pdf"
            had_previous = out_path.is_symlink() or out_path.is_file()
            if had_previous:
                copyfile(out_path, previous, follow_symlinks=False)
            staged.replace(out_path)
            try:
                session.commit()
            except BaseException:
                if had_previous:
                    previous.replace(out_path)
                else:
                    out_path.unlink(missing_ok=True)
                raise
    if job is not None:
        try:
            export_job_artifacts(session, job_id, base=output_base)
        except (OSError, TenantPathError):
            logger.warning(
                "could not update artifact export for job %s", job_id, exc_info=True
            )
    return out_path
