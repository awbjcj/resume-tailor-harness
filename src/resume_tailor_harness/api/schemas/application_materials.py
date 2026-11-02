"""Read-only material selection shared by clipboard and external handoffs."""

from typing import Literal

from pydantic import Field

from resume_tailor_harness.api.schemas.base import CamelModel


class ApplicationMaterialOut(CamelModel):
    id: int
    kind: Literal["resume", "cover_letter"]
    is_selected: bool
    application_eligible: bool
    block_reason: (
        Literal["fact_lock_failed", "fact_check_failed", "material_missing"] | None
    ) = None
    pdf_available: bool
    # Only eligible, tenant-confined PDFs receive a route. Never a server path.
    download_path: str | None = None


class ApplicationMaterialsOut(CamelModel):
    selected_resume_version_id: int | None = None
    selected_cover_letter_id: int | None = None
    items: list[ApplicationMaterialOut] = Field(default_factory=list)
