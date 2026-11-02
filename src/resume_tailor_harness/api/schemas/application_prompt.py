from typing import Literal

from resume_tailor_harness.api.schemas.base import CamelModel
from resume_tailor_harness.api.schemas.application_materials import (
    ApplicationMaterialsOut,
)


class ApplicationPromptOut(CamelModel):
    prompt: str
    materials: ApplicationMaterialsOut | None = None
    submission_policy: Literal["stop_before_submit"] = "stop_before_submit"
