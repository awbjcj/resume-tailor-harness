"""Admin-controlled provider routing backed by the deployment .env file."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from resume_tailor_harness.api.deps import refresh_platform_settings, require_admin
from resume_tailor_harness.api.errors import ApiException
from resume_tailor_harness.api.schemas.admin_routing import (
    ProviderRoutingStatus,
    RoutingConfigDoc,
    RoutingKeyStatus,
    RoutingUpdate,
)
from resume_tailor_harness.llm_routing import RouteConfigError
from resume_tailor_harness.provider_registry import PROVIDER_LABELS
from resume_tailor_harness.services.admin_routing import (
    RoutingState,
    routing_state,
    update_routing_settings,
)
from resume_tailor_harness.tenancy.context import UserContext
from resume_tailor_harness.api.schemas.admin_decisions import (
    DecisionsConfigDoc,
    DecisionsUpdate,
)
from resume_tailor_harness.config import Settings
from resume_tailor_harness.decisions import ENDPOINT, MODEL
from resume_tailor_harness.services.admin_decisions import update_decisions_settings

router = APIRouter(prefix="/admin/routing", tags=["admin"])


def _decisions_document(settings: Settings) -> DecisionsConfigDoc:
    return DecisionsConfigDoc(
        enabled=settings.openai_decisions_enabled,
        key_configured=bool(settings.openai_decisions_api_key.strip()),
        endpoint=ENDPOINT,
        model=MODEL,
    )


@router.get("/decisions")
def get_decisions_config(
    request: Request, _context: UserContext = Depends(require_admin)
) -> DecisionsConfigDoc:
    return _decisions_document(request.app.state.settings)


@router.put("/decisions")
def put_decisions_config(
    body: DecisionsUpdate,
    request: Request,
    _context: UserContext = Depends(require_admin),
) -> DecisionsConfigDoc:
    try:
        fresh = update_decisions_settings(
            request.app.state.settings,
            body.model_dump(exclude_unset=True),
            request.app.state.env_path,
        )
    except ValueError as exc:
        raise ApiException(422, "INVALID_DECISIONS_CONFIG", str(exc)) from exc
    refresh_platform_settings(request.app, fresh)
    return _decisions_document(fresh)


def _document(state: RoutingState) -> RoutingConfigDoc:
    return RoutingConfigDoc(
        base_url=state.base_url,
        providers=[
            ProviderRoutingStatus(
                provider=item.provider,
                label=PROVIDER_LABELS[item.provider],
                route_mode=item.route_mode,
                effective_mode=item.effective_mode,
                configuration_error=item.configuration_error,
                key=RoutingKeyStatus.model_validate(item.key),
            )
            for item in state.providers
        ],
    )


@router.get("")
def get_routing(
    request: Request, _context: UserContext = Depends(require_admin)
) -> RoutingConfigDoc:
    return _document(routing_state(request.app.state.settings))


@router.put("")
def put_routing(
    body: RoutingUpdate,
    request: Request,
    _context: UserContext = Depends(require_admin),
) -> RoutingConfigDoc:
    provided = body.model_dump(exclude_unset=True)
    try:
        fresh = update_routing_settings(
            request.app.state.settings, provided, request.app.state.env_path
        )
    except RouteConfigError as exc:
        raise ApiException(422, "INVALID_ROUTING_CONFIG", str(exc)) from exc
    refresh_platform_settings(request.app, fresh)
    return _document(routing_state(fresh))
