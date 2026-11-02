"""Material eligibility, explicit selections and upload availability in one place."""

from collections.abc import Iterable, Mapping, Sequence

from sqlmodel import Session, col, select

from resume_tailor_harness.api.schemas.application_materials import (
    ApplicationMaterialOut,
    ApplicationMaterialsOut,
)
from resume_tailor_harness.tailor.verdict import (
    DEFAULT_GATE_REVIEWERS,
    DETERMINISTIC_GATES,
)
from resume_tailor_harness.tenancy.storage import resolve_artifact_pdf
from resume_tailor_harness.tracking.tables import (
    Application,
    CoverLetter,
    ResumeVersion,
)


class MaterialSelectionError(ValueError):
    """A known document fails the application's factual safety requirements."""


def resume_application_eligible(
    fact_check_passed: bool,
    critiques: Sequence[Mapping[str, object]] | None = None,
    gate_reviewers: Iterable[str] | None = None,
) -> bool:
    """Scalar-friendly rule for selection, handoffs and batched continuation reads.

    A recorded roster (including an empty one) preserves the historical verdict.
    Deterministic gates always apply; legacy rosters use the shipped gate default.
    """
    gates = DETERMINISTIC_GATES | (
        frozenset(gate_reviewers)
        if gate_reviewers is not None
        else DEFAULT_GATE_REVIEWERS
    )
    return fact_check_passed and not any(
        critique.get("reviewer") in gates and critique.get("passed") is not True
        for critique in critiques or ()
    )


def material_for_application(
    row: ResumeVersion | CoverLetter, *, is_selected: bool = False
) -> ApplicationMaterialOut:
    assert row.id is not None
    is_resume = isinstance(row, ResumeVersion)
    eligible = (
        resume_application_eligible(
            row.fact_check_passed, row.critique_json, row.gate_reviewers_json
        )
        if isinstance(row, ResumeVersion)
        else row.fact_check_passed
    )
    pdf_available = resolve_artifact_pdf(row.pdf_path) is not None
    route = "resume-versions" if is_resume else "cover-letters"
    return ApplicationMaterialOut(
        id=row.id,
        kind="resume" if is_resume else "cover_letter",
        is_selected=is_selected,
        application_eligible=eligible,
        block_reason=None
        if eligible
        else "fact_lock_failed"
        if is_resume
        else "fact_check_failed",
        pdf_available=pdf_available,
        download_path=f"/api/{route}/{row.id}/pdf"
        if eligible and pdf_available
        else None,
    )


def application_materials(session: Session, job_id: int) -> ApplicationMaterialsOut:
    """Read exact selections without creating, replacing or clearing any pointers."""
    application = session.exec(
        select(Application)
        .where(Application.job_id == job_id)
        .order_by(col(Application.id))
    ).first()
    selected_resume = application.resume_version_id if application else None
    selected_letter = application.cover_letter_id if application else None
    items: list[ApplicationMaterialOut] = []
    for model, selected_id, kind in (
        (ResumeVersion, selected_resume, "resume"),
        (CoverLetter, selected_letter, "cover_letter"),
    ):
        rows = session.exec(
            select(model).where(model.job_id == job_id).order_by(col(model.id).desc())
        ).all()
        found_selected = False
        for row in rows:
            selected = row.id == selected_id
            found_selected |= selected
            item = material_for_application(row, is_selected=selected)
            if item.application_eligible or selected:
                items.append(item)
        if selected_id is not None and not found_selected:
            # Dangling or wrong-job legacy pointers stay visible, without reading
            # another job's document or implying that it is safe to upload.
            items.append(
                ApplicationMaterialOut(
                    id=selected_id,
                    kind="resume" if kind == "resume" else "cover_letter",
                    is_selected=True,
                    application_eligible=False,
                    block_reason="material_missing",
                    pdf_available=False,
                )
            )
    return ApplicationMaterialsOut(
        selected_resume_version_id=selected_resume,
        selected_cover_letter_id=selected_letter,
        items=items,
    )


def material_prompt(
    materials: ApplicationMaterialsOut, *, harness_url: str | None = None
) -> str:
    blocks = [
        "## Application materials\n\n"
        "Document selection prepares this application; it does not record submission. "
        "Preserve the exact selected IDs, including an older version. Never substitute "
        "a newer document automatically. This prompt does not attach any files. "
        "Confirm that the external assistant can authenticate to Resume Harness, "
        "download a file and upload it in the employer's browser. Download routes "
        "are relative to the Resume Harness app, not the employer site; they require "
        "an authenticated session or a configured SDK. Never paste API tokens into "
        "an employer site, prompt or URL. If those capabilities are unavailable, "
        "ask the user to download and provide the selected files."
    ]
    if harness_url:
        blocks.append(f"Resume Harness app: {harness_url}")
    for kind, label, selected in (
        ("resume", "Resume", materials.selected_resume_version_id),
        ("cover_letter", "Cover letter", materials.selected_cover_letter_id),
    ):
        if selected is None:
            blocks.append(
                f"- {label}: none selected. Ask which document to use if required."
            )
        for item in materials.items:
            if item.kind != kind:
                continue
            state = (
                "selected for application"
                if item.is_selected
                else "available alternative; not selected"
            )
            if not item.application_eligible:
                reason = (
                    "document is missing"
                    if item.block_reason == "material_missing"
                    else "factual safety check failed"
                )
                state += f"; BLOCKED: {reason}; do not upload; ask the user to change or clear this selection"
            elif item.download_path:
                state += f"; PDF available through {item.download_path}"
            else:
                state += "; PDF unavailable; render or request this exact file before uploading"
            blocks.append(f"- {label} #{item.id}: {state}.")
    return "\n\n".join(blocks) + "\n"
