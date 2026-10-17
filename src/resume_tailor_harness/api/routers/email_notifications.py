from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from resume_tailor_harness.api import attempts
from resume_tailor_harness.api.deps import get_engine
from resume_tailor_harness.api.errors import ApiException
from resume_tailor_harness.api.schemas.auth_email import CodeSentResponse
from resume_tailor_harness.api.schemas.email_notifications import (
    EmailNotificationOut,
    EmailNotificationUpdate,
    NotificationVerification,
)
from resume_tailor_harness.mail.tables import EmailNotificationPreference
from resume_tailor_harness.services import email_notifications as service
from resume_tailor_harness.tenancy.system_db import User
from resume_tailor_harness.tenancy.workspace import workspace_paths


router = APIRouter(prefix="/email-notifications", tags=["email-notifications"])
public_router = APIRouter(prefix="/email-notifications", tags=["email-notifications"])
T = TypeVar("T")


def _call(action: Callable[[], T]) -> T:
    try:
        return action()
    except service.NotificationError as error:
        raise ApiException(error.status, error.code, str(error)) from error


def _out(row: EmailNotificationPreference, request: Request) -> EmailNotificationOut:
    return EmailNotificationOut(
        **{key: getattr(row, key) for key in EmailNotificationUpdate.model_fields},
        verified_at=service.utc(row.verified_at) if row.verified_at else None,
        verification_pending=bool(
            row.code_hash
            and row.expires_at
            and service.utc(row.expires_at) > service.now_utc()
            and row.attempts < 5
        ),
        next_send_at=service.utc(row.next_send_at) if row.next_send_at else None,
        last_sent_at=service.utc(row.last_sent_at) if row.last_sent_at else None,
        delivery_available=service.delivery_available(request.app.state.settings),
        delivery_failed=row.delivery_failures > 0,
    )


@router.get("", response_model=EmailNotificationOut)
def get_preferences(request: Request, engine: Engine = Depends(get_engine)):
    return _out(service.get_preference(engine), request)


@router.put("", response_model=EmailNotificationOut)
def put_preferences(
    body: EmailNotificationUpdate,
    request: Request,
    engine: Engine = Depends(get_engine),
):
    return _out(service.update_preference(engine, body.model_dump()), request)


@router.post("/verification", response_model=CodeSentResponse)
def send_verification(request: Request, engine: Engine = Depends(get_engine)):
    system_engine = request.app.state.system_engine
    reserve_send: Callable[[str], bool] | None = None
    if system_engine is not None:

        def reserve(email: str, rate_engine: Engine = system_engine) -> bool:
            return attempts.consume(
                rate_engine,
                email=f"notification:{email}",
                ip=request.client.host if request.client else "unknown",
                scopes=attempts.RESEND_ONLY,
            )

        reserve_send = reserve
        row = service.get_preference(engine)
        if not attempts.consume(
            system_engine,
            email=f"notification:{row.email}",
            ip=request.client.host if request.client else "unknown",
            scopes=attempts.DEFAULT_SCOPES,
        ):
            raise ApiException(
                429,
                "RATE_LIMITED",
                "Please wait before requesting another verification code.",
            )
    _call(
        lambda: service.request_verification(
            engine,
            request.app.state.mailer,
            request.app.state.settings,
            reserve_send=reserve_send,
        )
    )
    return CodeSentResponse()


@router.post("/verify", response_model=EmailNotificationOut)
def verify(
    body: NotificationVerification,
    request: Request,
    engine: Engine = Depends(get_engine),
):
    row = _call(
        lambda: service.verify_address(
            engine, str(body.email), body.code, request.app.state.settings
        )
    )
    return _out(row, request)


def _unsubscribe_engine(request: Request, user_id: str) -> Engine:
    state = request.app.state
    if state.system_engine is None:
        if user_id == "local":
            return state.engine
    else:
        with Session(state.system_engine) as session:
            user = session.get(User, user_id)
            if user is not None and user.disabled_at is None:
                paths = workspace_paths(state.data_dir, user.id)
                return state.engine_registry.get(user.id, paths.db_url)
    raise ApiException(404, "INVALID_LINK", "This unsubscribe link is invalid.")


def _page(content: str) -> HTMLResponse:
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Email notifications</title></head><body><main>'
        + content
        + "</main></body></html>",
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; form-action 'self'; frame-ancestors 'none'",
        },
    )


@public_router.get(
    "/unsubscribe/{user_id}/{token}",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def unsubscribe_confirmation(user_id: str, token: str, request: Request):
    # GET never mutates consent: email security scanners routinely follow links.
    return _page(
        '<h1>Unsubscribe from email notifications?</h1><p>Account security emails will continue.</p><form method="post"><button type="submit">Unsubscribe</button></form>'
    )


@public_router.post(
    "/unsubscribe/{user_id}/{token}",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def unsubscribe(user_id: str, token: str, request: Request):
    if not service.unsubscribe(_unsubscribe_engine(request, user_id), token):
        raise ApiException(404, "INVALID_LINK", "This unsubscribe link is invalid.")
    return _page(
        "<h1>You are unsubscribed</h1><p>Email notifications are off. You can opt in again in Settings → Email notifications.</p>"
    )
