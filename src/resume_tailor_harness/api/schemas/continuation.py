from __future__ import annotations

from resume_tailor_harness.api.schemas.base import CamelModel
from resume_tailor_harness.services.application_continuation import NextStepKind


class ApplicationNextStepOut(CamelModel):
    job_id: int
    kind: NextStepKind
    href: str
    resume_version_id: int | None = None
