"""Configure the initial credential and model tiers in one workspace write."""

from collections.abc import Iterator
from pathlib import Path

from resume_tailor_harness.config import Settings
from resume_tailor_harness.llm_routing import (
    RouteConfigError,
    effective_mode,
    validate_base_url,
)
from resume_tailor_harness.llm_runner import (
    MODEL_CATALOG,
    model_access_available,
    split_provider,
)
from resume_tailor_harness.local_provider import (
    LocalProviderEndpoint,
    local_provider_endpoint,
    local_provider_updates,
)
from resume_tailor_harness.provider_registry import provider_spec
from resume_tailor_harness.services.env_config import write_env_updates

TIERS = ("cheap", "mid", "premium")
STARTER_MODELS = {
    "openai": ("openai:gpt-6-luna", "openai:gpt-6.1-terra", "openai:gpt-6.1-sol"),
    "anthropic": ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5"),
    "gemini": (
        "gemini:gemini-3.5-flash-lite",
        "gemini:gemini-3.8-flash",
        "gemini:gemini-4-argon",
    ),
    "deepseek": (
        "deepseek:deepseek-flash",
        "deepseek:deepseek-v4-pro",
        "deepseek:deepseek-v4-pro",
    ),
}


class ProviderSetupError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def tier_models(settings: Settings) -> tuple[str, str, str]:
    return settings.cheap_model, settings.mid_model, settings.premium_model


def setup_model_available(model_id: str, settings: Settings) -> bool:
    try:
        return model_access_available(model_id, settings=settings)
    except RouteConfigError:
        return False


def available_native_models(
    provider: str, settings: Settings, endpoint: LocalProviderEndpoint | None
) -> Iterator[str]:
    return (
        entry.id
        for entry in MODEL_CATALOG[provider]
        if (
            endpoint is None
            or split_provider(entry.id) != (endpoint.provider, endpoint.model)
        )
        and setup_model_available(entry.id, settings)
    )


def save_initial_provider(
    *,
    settings: Settings,
    env_path: Path,
    provider: str,
    api_key: str,
    base_url: str | None,
    model_id: str | None,
    allow_local_endpoint: bool,
    current_endpoint: LocalProviderEndpoint | None,
) -> Settings:
    spec = provider_spec(provider)
    if spec is None:
        raise ProviderSetupError("INVALID_PROVIDER", "Choose a supported provider.")
    key = api_key.strip()
    if key and (
        not key.isascii()
        or any(char.isspace() or not char.isprintable() for char in key)
    ):
        raise ProviderSetupError(
            "INVALID_API_KEY",
            "Enter an API key with printable ASCII characters and no spaces.",
        )

    if model_id is not None and base_url is None:
        raise ProviderSetupError(
            "INVALID_BASE_URL", "Enter the API base URL for this model."
        )
    if base_url is not None:
        if not allow_local_endpoint:
            raise ProviderSetupError(
                "CUSTOM_ENDPOINT_UNAVAILABLE",
                "Custom endpoints are available in local setup.",
            )
        try:
            url = validate_base_url(base_url, "API base URL")
        except RouteConfigError:
            url = ""
        if not url:
            raise ProviderSetupError(
                "INVALID_BASE_URL", "Enter a valid HTTP or HTTPS API base URL."
            )
        model = (model_id or "").strip()
        if not model or any(char.isspace() or not char.isprintable() for char in model):
            raise ProviderSetupError(
                "INVALID_MODEL_ID", "Enter the exact model ID from your provider."
            )

        def custom_updates(current: dict[str, str]) -> dict[str, str]:
            saved = local_provider_endpoint(current)
            endpoint_key = key
            if (
                not endpoint_key
                and saved
                and (saved.provider, saved.base_url) == (provider, url)
            ):
                endpoint_key = saved.api_key
            if not endpoint_key:
                raise ProviderSetupError(
                    "API_KEY_REQUIRED", "Enter an API key for this endpoint."
                )
            endpoint = LocalProviderEndpoint(provider, url, model, endpoint_key)
            return {
                **local_provider_updates(endpoint),
                **_tier_updates((endpoint.model_id,) * len(TIERS)),
            }

        return write_env_updates(custom_updates, env_path)

    try:
        mode = effective_mode(provider, settings)
    except RouteConfigError:
        raise ProviderSetupError(
            "PROVIDER_UNAVAILABLE",
            "This provider is unavailable. Choose another provider.",
        ) from None
    starters = STARTER_MODELS[provider]
    if not key or mode == "subscription":
        available = list(available_native_models(provider, settings, current_endpoint))
        if not available:
            if mode == "subscription":
                raise ProviderSetupError(
                    "PROVIDER_UNAVAILABLE",
                    "This provider is unavailable. Choose another provider.",
                )
            raise ProviderSetupError(
                "API_KEY_REQUIRED", "Enter an API key for this provider."
            )
        # A hosted plan can allow only some models from a provider. Choose a
        # funded model for any tier whose starter is unavailable to the user.
        starters = tuple(
            model if model in available else available[0] for model in starters
        )

    updates = _tier_updates(starters)
    if key:
        updates[spec.api_key_field.upper()] = key
    if allow_local_endpoint:
        updates.update(local_provider_updates(None))
    return write_env_updates(updates, env_path)


def _tier_updates(models: tuple[str, ...]) -> dict[str, str]:
    return {
        field: value
        for tier, model in zip(TIERS, models, strict=True)
        for field, value in (
            (f"{tier.upper()}_MODEL", model),
            (f"{tier.upper()}_REASONING_EFFORT", ""),
        )
    }
