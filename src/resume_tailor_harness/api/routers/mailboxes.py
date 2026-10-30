"""Mailbox routes. The OAuth callback uses one-time, browser-bound PKCE state."""

import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from resume_tailor_harness.api import auth
from resume_tailor_harness.api.deps import (
    get_data_dir,
    get_engine,
    get_run_manager,
    get_settings_dep,
)
from resume_tailor_harness.api.public_url import public_url
from resume_tailor_harness.api.errors import ErrorResponse
from resume_tailor_harness.api.routers.auth_google import (
    _store_oauth_flow,
    _consume_oauth_flow,
)
from resume_tailor_harness.api.runs.launch import launch
from resume_tailor_harness.api.schemas.runs import RunOut
from resume_tailor_harness.config import get_settings
from resume_tailor_harness.mailboxes import microsoft, store
from resume_tailor_harness.mailboxes.models import (
    MailboxAuthOut,
    MailboxConnectIn,
    MailboxError,
    MailboxOut,
    MailboxesOut,
)
from resume_tailor_harness.services import mailboxes
from resume_tailor_harness.tenancy.context import current_context, use_context

router = APIRouter(
    prefix="/mailboxes",
    tags=["mailboxes"],
    responses={
        409: {
            "model": ErrorResponse,
            "description": "Mailbox operation conflict or reconnection required",
        },
        422: {
            "model": ErrorResponse,
            "description": "Invalid connection settings or credentials",
        },
        502: {"model": ErrorResponse, "description": "Invalid email provider response"},
        503: {
            "model": ErrorResponse,
            "description": "Email provider or storage unavailable",
        },
    },
)
callback_router = APIRouter()
COOKIE = "mailbox_oauth_flow"
CALLBACK = "/api/mailboxes/microsoft/callback"


@router.get("", response_model=MailboxesOut)
def list_mailboxes(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return MailboxesOut(
        providers=mailboxes.providers(get_settings_dep(request)),
        accounts=[
            store.public_account(a)
            for a in store.read_accounts(get_data_dir(request)).values()
        ],
    )


@router.post("", response_model=MailboxOut, status_code=201)
def connect_mailbox(body: MailboxConnectIn, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return mailboxes.connect_custom(body, get_data_dir(request))


@router.delete("/{account_id}", status_code=204)
def disconnect_mailbox(account_id: str, request: Request):
    mailboxes.disconnect(account_id, get_data_dir(request))
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/{account_id}/sync", response_model=RunOut, status_code=202)
def sync_mailbox(account_id: str, request: Request):
    data_dir = get_data_dir(request)
    if account_id not in store.read_accounts(data_dir):
        from resume_tailor_harness.api.errors import ApiException

        raise ApiException(404, "NOT_FOUND", "Mailbox connection not found.")
    engine, settings = get_engine(request), get_settings_dep(request)

    def work(reporter):
        return mailboxes.run_mailbox_sync(
            engine,
            reporter,
            account_id=account_id,
            data_dir=data_dir,
            settings=settings,
        )

    return launch(
        get_run_manager(request),
        "mailboxSync",
        work,
        singleton_key="gmailSync",
        singleton_conflict="raise",
        meta={"accountId": account_id},
    )


@router.get("/microsoft/connect", response_model=MailboxAuthOut)
def microsoft_connect(request: Request, response: Response):
    settings = get_settings_dep(request)
    if not microsoft.available(settings):
        raise MailboxError(
            "Microsoft sign-in is not configured. Ask the administrator to configure its OAuth client."
        )
    context = current_context()
    verifier = secrets.token_urlsafe(48)
    state = (
        auth.issue_link_token(
            request.app.state.settings, user_id=context.user_id, purpose="mailbox-oauth"
        )
        if context
        else secrets.token_urlsafe(32)
    )
    if context and request.app.state.app_mode == "local":
        # Local workspaces do not require SESSION_SECRET. The durable flow row,
        # opaque cookie, and PKCE verifier bind this one-time state to its owner.
        state = f"local:{context.user_id}:{secrets.token_urlsafe(24)}"
    engine = request.app.state.system_engine
    if engine is not None:
        cookie = _store_oauth_flow(engine, state=state, verifier=verifier)
    else:
        cookie = secrets.token_urlsafe(32)
        flows = request.app.state.mailbox_oauth_states
        now = time.time()
        for key in list(flows):
            if flows[key][2] < now:
                flows.pop(key)
        if len(flows) >= 100:
            raise MailboxError("Too many pending connections. Try again later.")
        flows[cookie] = (state, verifier, now + 600)
    response.set_cookie(
        COOKIE,
        cookie,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies or request.url.scheme == "https",
        path=CALLBACK,
    )
    response.headers["Cache-Control"] = "no-store"
    return MailboxAuthOut(
        auth_url=microsoft.authorization_url(
            settings, public_url(request, CALLBACK), state, verifier
        )
    )


def _finish(outcome: str):
    response = RedirectResponse("/settings/notifications?mailbox=" + outcome)
    response.delete_cookie(COOKIE, path=CALLBACK)
    response.headers["Cache-Control"] = "no-store"
    return response


def _save_connection(request: Request, code: str, verifier: str, data_dir: Path):
    settings = get_settings() if current_context() else request.app.state.settings
    with store.connection_lock(data_dir):
        account = microsoft.connect(
            settings, public_url(request, CALLBACK), code, verifier
        )
        store.save_account(account, data_dir)


@callback_router.get(CALLBACK.removeprefix("/api"), include_in_schema=False)
def microsoft_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
):
    engine = request.app.state.system_engine
    cookie = request.cookies.get(COOKIE)
    if engine is None:
        flow = request.app.state.mailbox_oauth_states.pop(cookie, None)
        verifier = (
            flow[1]
            if flow
            and flow[2] >= time.time()
            and secrets.compare_digest(flow[0], state)
            else None
        )
    else:
        verifier = _consume_oauth_flow(engine, flow_cookie=cookie, state=state)
    if not verifier:
        return _finish("invalid")
    if error:
        return _finish("denied")
    if not code:
        return _finish("invalid")
    try:
        if engine is None:
            _save_connection(request, code, verifier, request.app.state.data_dir)
        else:
            from sqlalchemy.orm import Session
            from resume_tailor_harness.tenancy.system_db import User
            from resume_tailor_harness.tenancy.bootstrap import build_context

            user_id = auth.verify_link_token(
                state, request.app.state.settings, purpose="mailbox-oauth"
            )
            if request.app.state.app_mode == "local" and state.startswith("local:"):
                parts = state.split(":")
                default = request.app.state.default_context
                if len(parts) == 3 and default and parts[1] == default.user_id:
                    user_id = default.user_id
            with Session(engine, expire_on_commit=False) as session:
                user = session.get(User, user_id) if user_id else None
                if user is None or user.disabled_at is not None:
                    return _finish("invalid")
                session.expunge(user)
            context = build_context(
                user,
                request.app.state.data_dir,
                request.app.state.settings,
                request.app.state.engine_registry,
                system_engine=engine,
                template_dir=request.app.state.template_config_dir,
            )
            with use_context(context):
                _save_connection(request, code, verifier, context.paths.root)
    except Exception:  # OAuth/provider exceptions may contain tokens; never log them.
        return _finish("error")
    return _finish("connected")
