from resume_tailor_harness.api.schemas.base import CamelModel


class ApplicationPromptOut(CamelModel):
    prompt: str
