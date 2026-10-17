from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session
from sqlmodel import col

from resume_tailor_harness.api import auth
from resume_tailor_harness.api.deps import require_admin
from resume_tailor_harness.api.errors import ApiException
from resume_tailor_harness.api.schemas.admin_users import (
    AdminUser,
    AdminUserList,
    AdminUserPatch,
    ResetPasswordRequest,
)
from resume_tailor_harness.mail.account_notifications import enqueue_account_email
from resume_tailor_harness.tenancy.context import UserContext
from resume_tailor_harness.tenancy.limits import weekly_usage
from resume_tailor_harness.tenancy.payments import BillingError, require_closed_billing
from resume_tailor_harness.tenancy.system_db import AccountEmail, ApiToken, User
from resume_tailor_harness.tenancy.workspace import workspace_paths
from resume_tailor_harness.tracking.tables import Job

router = APIRouter(prefix="/admin/users", tags=["admin"])


def _last_admin(session: Session) -> bool:
    count = session.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == "admin", col(User.disabled_at).is_(None))
    ).scalar_one()
    return int(count) <= 1


def _active_jobs(request: Request, user_id: str) -> int:
    paths = workspace_paths(request.app.state.data_dir, user_id)
    if not paths.db_file.is_file():
        return 0
    engine = request.app.state.engine_registry.get(user_id, paths.db_url)
    with Session(engine) as session:
        return int(
            session.execute(
                select(func.count())
                .select_from(Job)
                .where(col(Job.archived_at).is_(None))
            ).scalar_one()
        )


def _account_settings(user: User) -> dict[str, str]:
    return {
        "Role": "Administrator" if user.role == "admin" else "Member",
        "Account access": "Disabled" if user.disabled_at else "Enabled",
        "Shared-key access": "Granted" if user.shared_key_access else "Revoked",
        "Active job limit": (
            "System default" if user.max_active_jobs is None else str(user.max_active_jobs)
        ),
        "Concurrent run limit": (
            "System default" if user.max_concurrent_runs is None else str(user.max_concurrent_runs)
        ),
    }


@router.get("")
def list_users(
    request: Request, _context: UserContext = Depends(require_admin)
) -> AdminUserList:
    engine = request.app.state.system_engine
    with Session(engine) as session:
        rows = session.execute(select(User).order_by(User.created_at)).scalars().all()
        return AdminUserList(
            users=[
                AdminUser(
                    id=row.id,
                    username=row.username,
                    role=row.role,
                    created_at=row.created_at,
                    disabled_at=row.disabled_at,
                    weekly_token_budget=row.weekly_token_budget,
                    max_active_jobs=row.max_active_jobs,
                    max_concurrent_runs=row.max_concurrent_runs,
                    shared_key_access=row.shared_key_access,
                    weekly_usage=weekly_usage(engine, row.id),
                    active_jobs=_active_jobs(request, row.id),
                )
                for row in rows
            ]
        )


@router.patch("/{user_id}")
def patch_user(
    user_id: str,
    body: AdminUserPatch,
    request: Request,
    context: UserContext = Depends(require_admin),
) -> dict[str, str]:
    if "weekly_token_budget" in body.model_fields_set:
        raise ApiException(
            422,
            "TOKEN_QUOTA_DEPRECATED",
            "Token budgets are analytics-only; manage this member's cost quota instead",
        )
    with Session(request.app.state.system_engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        user = session.get(User, user_id)
        if user is None:
            raise ApiException(404, "NOT_FOUND", "No such user")
        before = _account_settings(user)
        if body.role is not None and body.role != user.role:
            if body.role == "admin":
                try:
                    require_closed_billing(session, user_id)
                except BillingError as exc:
                    raise ApiException(exc.status, exc.code, str(exc)) from exc
            if user.role == "admin" and _last_admin(session):
                raise ApiException(409, "LAST_ADMIN", "Cannot demote the last admin")
            user.role = body.role
        if body.disabled is not None:
            if body.disabled and user.id == context.user_id:
                raise ApiException(409, "SELF_DISABLE", "Cannot disable yourself")
            user.disabled_at = datetime.now(timezone.utc) if body.disabled else None
        for field in ("max_active_jobs", "max_concurrent_runs"):
            if field in body.model_fields_set:
                setattr(user, field, getattr(body, field))
        if body.shared_key_access is not None:
            user.shared_key_access = body.shared_key_access
        changes = {
            label: f"{before[label]} → {value}"
            for label, value in _account_settings(user).items()
            if before[label] != value
        }
        if changes:
            enqueue_account_email(session, user, "account_updated", changes)
        session.commit()
    return {"status": "updated"}


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: str,
    body: ResetPasswordRequest,
    request: Request,
    _context: UserContext = Depends(require_admin),
) -> dict[str, str]:
    with Session(request.app.state.system_engine) as session:
        user = session.get(User, user_id)
        if user is None:
            raise ApiException(404, "NOT_FOUND", "No such user")
        user.password_hash = auth.hash_password(body.password)
        user.session_epoch += 1
        enqueue_account_email(session, user, "password_reset")
        session.commit()
    return {"status": "reset"}


@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    request: Request,
    confirm: str = "",
    context: UserContext = Depends(require_admin),
) -> dict[str, str]:
    if confirm != "DELETE":
        raise ApiException(400, "CONFIRM_REQUIRED", "Pass ?confirm=DELETE")
    if user_id == context.user_id:
        raise ApiException(409, "SELF_DELETE", "Cannot delete yourself")
    if request.app.state.run_manager.list_active(user_id=user_id):
        raise ApiException(409, "RUNS_ACTIVE", "The user has active runs")
    paths = workspace_paths(request.app.state.data_dir, user_id)
    tombstone = paths.root.with_name(f".{user_id}.deleting-{uuid.uuid4().hex}")
    user_values: dict[str, object]
    token_values: list[dict[str, object]]
    with Session(request.app.state.system_engine, expire_on_commit=False) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        user = session.get(User, user_id)
        if user is None:
            raise ApiException(404, "NOT_FOUND", "No such user")
        if user.role == "admin" and _last_admin(session):
            raise ApiException(409, "LAST_ADMIN", "Cannot delete the last admin")
        try:
            require_closed_billing(session, user_id)
        except BillingError as exc:
            raise ApiException(exc.status, exc.code, str(exc)) from exc
        request.app.state.engine_registry.evict(user_id)
        if paths.root.exists():
            paths.root.rename(tombstone)
        user_values = {
            column.name: getattr(user, column.name) for column in User.__table__.columns
        }
        tokens = (
            session.execute(select(ApiToken).where(ApiToken.user_id == user_id))
            .scalars()
            .all()
        )
        token_values = [
            {
                column.name: getattr(token, column.name)
                for column in ApiToken.__table__.columns
            }
            for token in tokens
        ]
        notice = enqueue_account_email(session, user, "account_deleted", ready=False)
        notice_id = notice.id if notice is not None else None
        try:
            session.execute(delete(ApiToken).where(ApiToken.user_id == user_id))
            session.delete(user)
            session.commit()
        except BaseException:
            session.rollback()
            if tombstone.exists() and not paths.root.exists():
                tombstone.rename(paths.root)
            raise
    try:
        shutil.rmtree(tombstone)
    except OSError as error:
        if tombstone.exists() and not paths.root.exists():
            tombstone.rename(paths.root)
        with Session(request.app.state.system_engine) as recovery:
            notice = recovery.get(AccountEmail, notice_id) if notice_id else None
            if notice is not None:
                recovery.delete(notice)
            if recovery.get(User, user_id) is None:
                recovery.add(User(**user_values))
                recovery.add_all(ApiToken(**values) for values in token_values)
            recovery.commit()
        raise ApiException(
            500,
            "DELETE_CLEANUP_FAILED",
            "Workspace cleanup failed; the user and workspace were restored",
        ) from error
    if notice_id:
        with Session(request.app.state.system_engine) as session:
            notice = session.get(AccountEmail, notice_id)
            if notice is not None:
                notice.ready = True
                session.commit()
    return {"status": "deleted"}
