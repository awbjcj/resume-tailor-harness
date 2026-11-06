"""A local workspace's custom connection, separate from platform credentials."""

from dataclasses import dataclass, field

from resume_tailor_harness.llm_routing import (
    RouteConfigError,
    provider_sdk_base_url,
    validate_base_url,
)
from resume_tailor_harness.provider_registry import PROVIDERS

_ENV_FIELDS = {
    "provider": "LOCAL_LLM_PROVIDER",
    "base_url": "LOCAL_LLM_BASE_URL",
    "model": "LOCAL_LLM_MODEL",
    "api_key": "LOCAL_LLM_API_KEY",
}
_EXACT_BASE_URL = "LOCAL_LLM_BASE_URL_EXACT"


@dataclass(frozen=True)
class LocalProviderEndpoint:
    provider: str
    base_url: str
    model: str
    api_key: str = field(repr=False)

    @property
    def model_id(self) -> str:
        return f"{self.provider}:{self.model}"


def local_provider_endpoint(env: dict[str, str]) -> LocalProviderEndpoint | None:
    provider, url, model, key = (env.get(name, "") for name in _ENV_FIELDS.values())
    if provider not in PROVIDERS or not (url and model and key):
        return None
    try:
        url = validate_base_url(url, "API base URL")
    except RouteConfigError:
        return None
    if url and env.get(_EXACT_BASE_URL) != "1":
        # Older workspace files saved an origin and let the SDK adapter add
        # its path. Preserve the effective endpoint on the first read.
        url = provider_sdk_base_url(provider, url) or url
    return LocalProviderEndpoint(provider, url, model, key) if url else None


def local_provider_updates(endpoint: LocalProviderEndpoint | None) -> dict[str, str]:
    updates = {
        var: getattr(endpoint, name) if endpoint else ""
        for name, var in _ENV_FIELDS.items()
    }
    updates[_EXACT_BASE_URL] = "1" if endpoint else ""
    return updates
