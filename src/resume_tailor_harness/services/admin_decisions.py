"""Deployment-only enrollment, independent of subscription routing."""

from pathlib import Path
from typing import Mapping

from resume_tailor_harness.config import Settings
from resume_tailor_harness.services.env_config import write_env_updates


def update_decisions_settings(
    current: Settings, provided: Mapping[str, object], env_path: Path
) -> Settings:
    enabled = provided.get("enabled", current.openai_decisions_enabled)
    if type(enabled) is not bool:
        raise ValueError("Enabled must be true or false")
    raw_key = provided.get("api_key", current.openai_decisions_api_key)
    key = str(raw_key or "").strip()
    if any(char.isspace() for char in key):
        raise ValueError("Enter an OpenAI API key without whitespace")
    if key and key == current.sub2api_openai_key:
        raise ValueError("Use an OpenAI API key, not the subscription gateway key")
    if enabled and not key:
        raise ValueError(
            "Add a direct OpenAI API key before enabling fast skill classification"
        )
    updates: dict[str, str] = {}
    if "enabled" in provided:
        updates["OPENAI_DECISIONS_ENABLED"] = str(enabled).lower()
    if "api_key" in provided:
        updates["OPENAI_DECISIONS_API_KEY"] = key
    return write_env_updates(updates, env_path)
