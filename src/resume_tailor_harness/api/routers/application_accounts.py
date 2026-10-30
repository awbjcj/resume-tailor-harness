"""Tenant-scoped vault management and explicit host-agent secret transport."""

from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlmodel import Session

from resume_tailor_harness.api.deps import get_config_store, get_data_dir, get_session
from resume_tailor_harness.api.errors import ApiException, ErrorResponse
from resume_tailor_harness.api.schemas.application_accounts import (
    AccountAccess,
    AccountOutcome,
    AccountOut,
    AccountPolicyUpdate,
    AccountPrepare,
    AccountPreparedOut,
    AccountSave,
    AccountSecretOut,
    AccountUpdate,
    AccountVaultOut,
)
from resume_tailor_harness.services.agent_applications import (
    ApplicationWorkflowError,
    read_profile,
)
from resume_tailor_harness.services.application_accounts import (
    AccountVault,
    AccountVaultError,
)
from resume_tailor_harness.tenancy.context import current_context


def _guard(request: Request, response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    if request.method in {"GET", "HEAD"}:
        return
    # Browser mutations are same-origin. PAT clients need no Origin header.
    origin = request.headers.get("origin")
    base = request.app.state.settings.app_base_url or str(request.base_url)
    parsed = urlsplit(base)
    expected = f"{parsed.scheme}://{parsed.netloc}"
    if (origin is not None and origin != expected) or (
        request.cookies and not request.headers.get("authorization") and origin is None
    ):
        raise ApiException(
            403,
            "CROSS_ORIGIN_REQUEST",
            "Password manager requests must come from this application",
        )


router = APIRouter(
    tags=["Application accounts"],
    dependencies=[Depends(_guard)],
    responses={
        code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 503)
    },
)


@contextmanager
def _errors() -> Iterator[None]:
    try:
        yield
    except AccountVaultError as exc:
        raise ApiException(exc.status, exc.code, str(exc)) from None
    except ApplicationWorkflowError as exc:
        raise ApiException(
            404 if exc.code == "NOT_FOUND" else 409, exc.code, str(exc)
        ) from None


def _vault(request: Request) -> AccountVault:
    context = current_context()
    root = get_data_dir(request)
    owner = str(context.user_id) if context is not None else str(root.resolve())
    # Always deployment-owned: workspace secrets cannot replace the key.
    return AccountVault(root, owner, request.app.state.settings.application_vault_keys)


@router.get("/application-accounts", response_model=AccountVaultOut)
def list_accounts(request: Request):
    with _errors():
        return _vault(request).status()


@router.patch("/application-accounts/policy", response_model=AccountVaultOut)
def update_policy(body: AccountPolicyUpdate, request: Request):
    with _errors():
        return _vault(request).policy(body)


@router.post("/application-accounts", response_model=AccountOut)
def save_account(body: AccountSave, request: Request):
    with _errors():
        return _vault(request).save(body)


@router.patch("/application-accounts/{account_id}", response_model=AccountOut)
def update_account(account_id: str, body: AccountUpdate, request: Request):
    with _errors():
        return _vault(request).update(account_id, body)


@router.delete("/application-accounts/{account_id}", status_code=204)
def delete_account(account_id: str, request: Request, revision: int = Query(ge=1)):
    with _errors():
        _vault(request).delete(account_id, revision)


@router.post(
    "/jobs/{job_id}/application-account/prepare", response_model=AccountPreparedOut
)
def prepare_account(
    job_id: int,
    body: AccountPrepare,
    request: Request,
    session: Session = Depends(get_session),
):
    with _errors():
        return _vault(request).prepare(
            session,
            job_id,
            body,
            default_username=read_profile(get_config_store(request)).profile.email,
        )


@router.post(
    "/jobs/{job_id}/application-accounts/{account_id}/secret",
    response_model=AccountSecretOut,
)
def account_secret(
    job_id: int,
    account_id: str,
    body: AccountAccess,
    request: Request,
    session: Session = Depends(get_session),
):
    with _errors():
        return _vault(request).secret(session, job_id, account_id, body)


@router.post(
    "/jobs/{job_id}/application-accounts/{account_id}/outcome",
    response_model=AccountOut,
)
def account_outcome(
    job_id: int,
    account_id: str,
    body: AccountOutcome,
    request: Request,
    session: Session = Depends(get_session),
):
    with _errors():
        return _vault(request).outcome(session, job_id, account_id, body)
