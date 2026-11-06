"""First-run readiness and provider configuration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from fastapi import APIRouter, Request, Response

from resume_tailor_harness.api.deps import (
    get_config_store,
    get_document_store,
    get_env_path,
    get_profile_dir,
    get_settings_dep,
    refresh_app_settings,
)
from resume_tailor_harness.api.errors import ApiException
from resume_tailor_harness.api.schemas.config import ProfileConfigDoc, SearchConfigDoc
from resume_tailor_harness.api.schemas.setup import (
    CareerSkillsCapabilityStatus,
    H1BCapabilityStatus,
    ProfileStatus,
    SearchStatus,
    SecretsStatus,
    SetupCapabilities,
    SetupCustomEndpoint,
    SetupProviderChoice,
    SetupProviderOut,
    SetupProviderUpdate,
    SetupStatusOut,
    SourcesStatus,
)
from resume_tailor_harness.career_skills.registry import CareerSkillRegistry
from resume_tailor_harness.llm_runner import MODEL_CATALOG, split_provider
from resume_tailor_harness.profile.conversation import (
    can_rebuild_without_resume,
    load_edits,
)
from resume_tailor_harness.profile.corpus import MANIFEST_NAME, doc_path, load_manifest
from resume_tailor_harness.profile.publication import publication_status
from resume_tailor_harness.provider_registry import PROVIDER_SPECS
from resume_tailor_harness.services.provider_setup import (
    ProviderSetupError,
    available_native_models,
    save_initial_provider,
    setup_model_available,
    tier_models,
)
from resume_tailor_harness.services.sources import list_sources
from resume_tailor_harness.tenancy.context import current_context

router = APIRouter()


@router.get("/setup/status", response_model=SetupStatusOut)
def get_setup_status(request: Request):
    settings = get_settings_dep(request)
    available_tiers = [
        setup_model_available(model, settings) for model in tier_models(settings)
    ]
    anthropic_key = any(
        setup_model_available(entry.id, settings)
        for entry in MODEL_CATALOG["anthropic"]
    )
    secrets = SecretsStatus(
        anthropic_key=anthropic_key,
        any_llm_key=any(available_tiers)
        or anthropic_key
        or any(
            setup_model_available(entry.id, settings)
            for provider, entries in MODEL_CATALOG.items()
            if provider != "anthropic"
            for entry in entries
        ),
        model_tiers_ready=all(available_tiers),
    )

    document_store = get_document_store(request)
    config_store = get_config_store(request)
    docs = document_store.list()
    profile_dir = get_profile_dir(request)
    manifest_exists = (profile_dir / MANIFEST_NAME).exists()
    sources = load_manifest(profile_dir).docs if manifest_exists else []
    facts_path = profile_dir / "facts.json"
    facts_built_at = (
        datetime.fromtimestamp(facts_path.stat().st_mtime, tz=timezone.utc).isoformat(
            timespec="seconds"
        )
        if facts_path.exists()
        else None
    )
    profile_cfg = cast(ProfileConfigDoc, config_store.get("profile"))
    publication = publication_status(profile_dir)
    profile = ProfileStatus(
        document_count=len(sources) if manifest_exists else len(docs),
        has_resume=any(
            d.primary and doc_path(profile_dir, d).is_file() for d in sources
        )
        if manifest_exists
        else any(d.doc_type == "resume" for d in docs),
        facts_built_at=facts_built_at,
        freshness=publication.freshness,
        published_at=publication.published_at,
        pending_source_count=publication.pending_source_count,
        github_username=profile_cfg.github_username,
    )
    try:
        profile.can_rebuild = not load_edits(profile_dir).deleted and (
            profile.has_resume or can_rebuild_without_resume(profile_dir)
        )
    except (OSError, ValueError):
        profile.can_rebuild = False

    search_cfg = cast(SearchConfigDoc, config_store.get("search"))
    search = SearchStatus(
        configured=bool(
            search_cfg.keywords or search_cfg.titles or search_cfg.role_anchors
        )
    )

    try:
        enabled = sum(
            1
            for v in list_sources(
                connectors_path=str(config_store.config_dir / "connectors.yaml"),
                settings=settings,
            )
            if v.enabled
        )
    except Exception:  # missing/broken connectors.yaml must not 500 the gate
        enabled = 0
    sources = SourcesStatus(enabled_count=enabled)

    try:
        skill_capabilities = CareerSkillRegistry.from_settings(
            settings
        ).public_capabilities()
    except Exception as exc:  # a readiness defect must not break the setup gate
        skill_capabilities = []
        skill_error = str(exc)
    else:
        skill_error = None
    available = sum(1 for row in skill_capabilities if row.is_available)
    unavailable = len(skill_capabilities) - available
    if skill_error:
        unavailable += 1

    complete = (
        all(available_tiers)
        and profile.can_rebuild
        and profile.facts_built_at is not None
        and search.configured
        and sources.enabled_count > 0
    )
    return SetupStatusOut(
        secrets=secrets,
        profile=profile,
        search=search,
        sources=sources,
        capabilities=SetupCapabilities(
            career_skills=CareerSkillsCapabilityStatus(
                available=available,
                unavailable=unavailable,
            ),
            h1b=H1BCapabilityStatus(
                capability="available" if settings.h1b_mcp_enabled else "disabled"
            ),
        ),
        complete=complete,
    )


@router.get("/setup/provider", response_model=SetupProviderOut)
def get_setup_provider(request: Request, response: Response) -> SetupProviderOut:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings_dep(request)
    context = current_context()
    endpoint = context.local_provider_endpoint if context else None
    choices = [
        SetupProviderChoice(
            id=spec.id,
            label=spec.label,
            available=next(available_native_models(spec.id, settings), None)
            is not None,
        )
        for spec in PROVIDER_SPECS
    ]
    models = tier_models(settings)
    ready = all(setup_model_available(model, settings) for model in models)
    providers = {split_provider(model)[0] for model in models}
    if len(providers) == 1:
        selected = providers.pop()
    elif ready:
        selected = None
    else:
        selected = next((choice.id for choice in choices if choice.available), "openai")
    return SetupProviderOut(
        providers=choices,
        selected_provider=selected,
        model_tiers_ready=ready,
        custom_endpoint_allowed=request.app.state.app_mode == "local"
        and context is not None,
        custom_endpoint=SetupCustomEndpoint(
            provider=endpoint.provider,
            base_url=endpoint.base_url,
            model_id=endpoint.model,
            selected=all(
                split_provider(model) == (endpoint.provider, endpoint.model)
                for model in models
            ),
        )
        if endpoint
        else None,
    )


@router.put("/setup/provider", status_code=204)
def put_setup_provider(body: SetupProviderUpdate, request: Request) -> None:
    context = current_context()
    try:
        fresh = save_initial_provider(
            settings=get_settings_dep(request),
            env_path=get_env_path(request),
            provider=body.provider,
            api_key=body.api_key.get_secret_value() if body.api_key else "",
            base_url=body.base_url,
            model_id=body.model_id,
            allow_local_endpoint=request.app.state.app_mode == "local"
            and context is not None,
        )
    except ProviderSetupError as exc:
        raise ApiException(422, exc.code, str(exc)) from None
    refresh_app_settings(request.app, fresh)
