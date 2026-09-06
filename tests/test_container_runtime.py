import os
from pathlib import Path

import pytest

from resume_tailor_harness.container_runtime import (
    _drop_privileges_to_app_user,
    configure_environment,
    resolve_app_mode,
)

ROOT = Path(__file__).resolve().parents[1]


def test_container_defaults_to_local_mode_without_hosted_settings():
    environment: dict[str, str] = {}

    mode = configure_environment(environment)

    assert mode == "local"
    assert environment["BROWSER_ENABLED"] == "false"
    assert environment["SECURE_COOKIES"] == "false"
    assert environment["DISABLE_API_DOCS"] == "false"


def test_container_auto_selects_secure_hosted_mode_from_public_origin():
    environment = {"APP_BASE_URL": "https://resume.example.com"}

    mode = configure_environment(environment)

    assert mode == "hosted"
    assert environment["SECURE_COOKIES"] == "true"
    assert environment["DISABLE_API_DOCS"] == "true"
    assert environment["REGISTRATION_MODE"] == "open"


def test_hosted_mode_preserves_safe_overrides_but_forces_secure_cookies():
    environment = {
        "APP_MODE": "hosted",
        "SECURE_COOKIES": "false",
        "DISABLE_API_DOCS": "false",
        "REGISTRATION_MODE": "invite",
    }

    assert configure_environment(environment) == "hosted"
    assert environment["SECURE_COOKIES"] == "true"
    assert environment["DISABLE_API_DOCS"] == "false"
    assert environment["REGISTRATION_MODE"] == "invite"


def test_invalid_container_mode_fails_loudly():
    with pytest.raises(ValueError, match="APP_MODE"):
        resolve_app_mode({"APP_MODE": "public"})


def test_image_creates_app_user_and_starts_as_root_and_does_not_copy_local_config():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    # The container starts as root so container_runtime.py can reclaim the
    # mounted /app/data volume before dropping to resume-tailor-harness -- a static
    # `USER resume-tailor-harness` here would skip that reclaim and reintroduce the
    # UID-drift permission failure it fixes.
    assert "useradd --system --gid resume-tailor-harness" in dockerfile
    assert "USER resume-tailor-harness" not in dockerfile
    assert 'ENTRYPOINT ["python", "-m", "resume_tailor_harness.container_runtime"]' in dockerfile
    assert "COPY config ./config.defaults" not in dockerfile
    assert "config/*" in dockerignore
    assert "!config/*.example" in dockerignore


def test_drop_privileges_is_a_noop_when_not_root():
    geteuid = getattr(os, "geteuid", None)
    if not callable(geteuid):
        pytest.skip("privilege drop is POSIX-only")
    assert geteuid() != 0
    _drop_privileges_to_app_user()


def test_compose_binds_localhost_and_persists_the_data_root():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert '"127.0.0.1:${RESUME_TAILOR_HARNESS_PORT:-8000}:8000"' in compose
    assert "APP_MODE: local" in compose
    assert "resume-tailor-harness-data:/app/data" in compose
    assert "seccomp:./deploy/playwright-seccomp.json" in compose


def test_optional_h1b_compose_profile_uses_private_network_and_persistent_cache():
    compose = (ROOT / "compose.h1b.yaml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile.h1b").read_text(encoding="utf-8")

    assert "profiles:" in compose
    assert "- h1b" in compose
    assert "H1B_MCP_ENABLED: \"true\"" in compose
    assert "H1B_MCP_URL: http://h1b-job-search-mcp:8000/mcp" in compose
    assert "condition: service_healthy" in compose
    assert "h1b-job-search-mcp-data:/app/data_cache" in compose
    assert "ports:" not in compose
    assert "dockerfile: Dockerfile.h1b" in compose
    assert "uv sync --frozen --no-dev --no-install-project" in dockerfile
    assert "USER h1b-job-search-mcp" in dockerfile


def test_windows_launcher_initializes_config_and_optional_h1b_service():
    launcher = (ROOT / "scripts" / "windows" / "Start-ResumeTailor.ps1").read_text(
        encoding="utf-8"
    )
    command_launcher = (
        ROOT / "scripts" / "windows" / "Start-ResumeTailor.cmd"
    ).read_text(encoding="utf-8")

    assert "git submodule update --init --recursive" in launcher
    assert "Copy-Item -LiteralPath $templateFile -Destination $envFile" in launcher
    assert "Docker Desktop is required" in launcher
    assert "compose.h1b.yaml" in launcher
    assert "--profile', 'h1b" in launcher
    assert "-ExecutionPolicy Bypass" in command_launcher
    assert "Start-ResumeTailor.ps1" in command_launcher
    assert "exit /b %ERRORLEVEL%" in command_launcher
