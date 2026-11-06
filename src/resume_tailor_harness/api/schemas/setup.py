"""Setup readiness projection for the first-run gate + dashboard health card."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, SecretStr

from resume_tailor_harness.api.schemas.base import CamelModel
from resume_tailor_harness.profile.publication import ProfileFreshness


class SecretsStatus(CamelModel):
    anthropic_key: bool
    any_llm_key: bool
    model_tiers_ready: bool | None = None


class SetupProviderChoice(CamelModel):
    id: str
    label: str
    available: bool


class SetupCustomEndpoint(CamelModel):
    provider: str
    base_url: str
    model_id: str
    selected: bool


class SetupProviderOut(CamelModel):
    providers: list[SetupProviderChoice]
    selected_provider: str | None
    model_tiers_ready: bool
    custom_endpoint_allowed: bool
    custom_endpoint: SetupCustomEndpoint | None = None


class SetupProviderUpdate(CamelModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(max_length=32)
    api_key: SecretStr | None = Field(default=None, max_length=4096)
    base_url: str | None = Field(default=None, max_length=2048)
    model_id: str | None = Field(default=None, max_length=256)


class ProfileStatus(CamelModel):
    document_count: int
    has_resume: bool
    can_rebuild: bool = False
    facts_built_at: str | None = None
    freshness: ProfileFreshness = "unknown"
    published_at: str | None = None
    pending_source_count: int = 0
    github_username: str | None = None


class SearchStatus(CamelModel):
    configured: bool


class SourcesStatus(CamelModel):
    enabled_count: int


class CareerSkillsCapabilityStatus(CamelModel):
    available: int
    unavailable: int


class H1BCapabilityStatus(CamelModel):
    capability: Literal["disabled", "available", "unavailable"]


class SetupCapabilities(CamelModel):
    career_skills: CareerSkillsCapabilityStatus
    h1b: H1BCapabilityStatus | None = None


class SetupStatusOut(CamelModel):
    secrets: SecretsStatus
    profile: ProfileStatus
    search: SearchStatus
    sources: SourcesStatus
    capabilities: SetupCapabilities | None = None
    complete: bool
