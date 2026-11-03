"""Admin enrollment in direct, metered skill classification."""

from pydantic import ConfigDict, Field

from resume_tailor_harness.api.schemas.base import CamelModel


class DecisionsConfigDoc(CamelModel):
    enabled: bool
    key_configured: bool
    endpoint: str
    model: str


class DecisionsUpdate(CamelModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    # Omitted = preserve; null/empty = remove. Never returned to the client.
    api_key: str | None = Field(default=None, max_length=512, repr=False)
