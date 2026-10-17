import json
import re
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_tailor_harness.mail.account_notifications import deliver_account_emails
from resume_tailor_harness.services.email_notification_scheduler import (
    email_notification_tick,
)
from resume_tailor_harness.tenancy.system_db import AccountEmail, User
from resume_tailor_harness.tenancy.workspace import provision_workspace


@pytest.fixture
def member(mu_app, mu_client):
    user_id = "alice0000000"
    with Session(mu_app.state.system_engine) as session:
        session.add(
            User(
                id=user_id,
                username="alice",
                password_hash="hash",
                role="user",
                email="alice@example.com",
                email_verified_at=datetime.now(UTC),
            )
        )
        session.commit()
    provision_workspace(
        mu_app.state.data_dir, user_id, template_dir=mu_app.state.template_config_dir
    )
    assert (
        mu_client.post(
            "/api/auth/login",
            json={"identifier": "owner", "password": "owner-password"},
        ).status_code
        == 200
    )
    return user_id


def notices(app):
    with Session(app.state.system_engine) as session:
        return list(session.scalars(select(AccountEmail)))


@pytest.mark.parametrize(
    "patch,detail,after",
    [
        ({"role": "admin"}, "Role", "Administrator"),
        ({"sharedKeyAccess": False}, "Shared-key access", "Revoked"),
        ({"disabled": True}, "Account access", "Disabled"),
        ({"maxActiveJobs": 30}, "Active job limit", "30"),
        ({"maxConcurrentRuns": 2}, "Concurrent run limit", "2"),
    ],
)
def test_admin_changes_notify_registered_address_once(
    mu_app, mu_client, member, patch, detail, after
):
    assert mu_client.patch(f"/api/admin/users/{member}", json=patch).status_code == 200
    rows = notices(mu_app)
    assert len(rows) == 1
    assert rows[0].recipient == "alice@example.com"
    assert json.loads(rows[0].context_json)["details"][detail].endswith(after)
    assert mu_client.patch(f"/api/admin/users/{member}", json=patch).status_code == 200
    assert len(notices(mu_app)) == 1


def test_admin_demotion_and_shared_access_grant(mu_app, mu_client, member):
    with Session(mu_app.state.system_engine) as session:
        user = session.get(User, member)
        assert user is not None
        user.role, user.shared_key_access = "admin", False
        session.commit()
    response = mu_client.patch(
        f"/api/admin/users/{member}", json={"role": "user", "sharedKeyAccess": True}
    )
    assert response.status_code == 200
    details = json.loads(notices(mu_app)[0].context_json)["details"]
    assert details == {
        "Role": "Administrator → Member",
        "Shared-key access": "Revoked → Granted",
    }


def test_failed_operation_never_queues_notice(mu_app, mu_client, member):
    with Session(mu_app.state.system_engine) as session:
        owner = session.scalar(select(User).where(User.username == "owner"))
        assert owner is not None
        owner.email, owner.email_verified_at = "owner@example.com", datetime.now(UTC)
        owner_id = owner.id
        session.commit()
    assert (
        mu_client.patch(
            f"/api/admin/users/{owner_id}", json={"role": "user"}
        ).status_code
        == 409
    )
    assert mu_client.delete(f"/api/admin/users/{member}").status_code == 400
    assert notices(mu_app) == []


def test_admin_reset_does_not_expose_password(mu_app, mu_client, member):
    password = "new-password-long"
    assert (
        mu_client.post(
            f"/api/admin/users/{member}/reset-password", json={"password": password}
        ).status_code
        == 200
    )
    row = notices(mu_app)[0]
    assert "password was reset" in json.loads(row.context_json)["title"]
    assert password not in row.context_json
    with Session(mu_app.state.system_engine) as session:
        user = session.get(User, member)
        assert user is not None
        assert user.session_epoch == 1


def test_delete_notice_survives_workspace_removal_and_failure_is_silent(
    mu_app, mu_client, member, monkeypatch
):
    from resume_tailor_harness.api.routers import admin_users

    original = admin_users.shutil.rmtree

    def fail_cleanup(path):
        # A dispatcher cannot send the held deletion notice mid-cleanup.
        settings = mu_app.state.settings.model_copy(update={"resend_api_key": "test"})
        assert (
            deliver_account_emails(
                mu_app.state.system_engine, mu_app.state.mailer, settings
            )
            == 0
        )
        raise OSError("failed cleanup")

    monkeypatch.setattr(admin_users.shutil, "rmtree", fail_cleanup)
    url = f"/api/admin/users/{member}?confirm=DELETE"
    assert mu_client.delete(url).status_code == 500
    assert notices(mu_app) == []
    monkeypatch.setattr(admin_users.shutil, "rmtree", original)
    assert mu_client.delete(url).status_code == 200
    row = notices(mu_app)[0]
    assert row.ready and row.recipient == "alice@example.com"
    assert not (mu_app.state.data_dir / "users" / member).exists()


def test_quota_override_and_tier_allowance_notices(mu_app, mu_client, member):
    assert (
        mu_client.patch(
            f"/api/admin/quota-accounts/{member}",
            json={"allowanceOverrideMicros": 4_000_000, "reason": "Adjustment"},
        ).status_code
        == 200
    )
    assert (
        json.loads(notices(mu_app)[0].context_json)["title"]
        == "Your quota allowance was changed"
    )
    assert (
        mu_client.patch(
            f"/api/admin/quota-accounts/{member}",
            json={"allowanceOverrideMicros": None, "reason": "Restore default"},
        ).status_code
        == 200
    )
    assert (
        mu_client.patch(
            "/api/admin/quota-tiers/FREE",
            json={"allowanceMicros": 3_000_000, "reason": "Tier update"},
        ).status_code
        == 200
    )
    assert (
        json.loads(notices(mu_app)[-1].context_json)["title"]
        == "Your tier allowance was changed"
    )


def test_security_operations_notify_without_exposing_secrets(mu_app, mu_client, member):
    with Session(mu_app.state.system_engine) as session:
        owner = session.scalar(select(User).where(User.username == "owner"))
        assert owner is not None
        owner.email, owner.email_verified_at, owner.google_sub = (
            "owner@example.com",
            datetime.now(UTC),
            "google-subject",
        )
        session.commit()
    created = mu_client.post("/api/account/tokens", json={"name": "Automation"})
    assert created.status_code == 201
    token = created.json()
    assert mu_client.delete(f"/api/account/tokens/{token['id']}").status_code == 204
    assert mu_client.delete(f"/api/account/tokens/{token['id']}").status_code == 204
    assert (
        mu_client.post(
            "/api/account/password",
            json={
                "currentPassword": "owner-password",
                "newPassword": "quartz-lantern-42-drift",
            },
        ).status_code
        == 200
    )
    assert mu_client.post("/api/account/sessions/revoke-all").status_code == 200
    assert mu_client.delete("/api/account/google").status_code == 200
    rows = notices(mu_app)
    assert [row.event for row in rows] == [
        "token_created",
        "token_revoked",
        "password_changed",
        "sessions_revoked",
        "google_unlinked",
    ]
    assert all(row.recipient == "owner@example.com" for row in rows)
    assert all(
        token["token"] not in row.context_json
        and "quartz-lantern-42-drift" not in row.context_json
        for row in rows
    )


def test_scheduler_sends_to_disabled_and_deleted_accounts_without_digest_opt_in(
    mu_app, mu_client, member
):
    assert (
        mu_client.patch(
            f"/api/admin/users/{member}", json={"disabled": True}
        ).status_code
        == 200
    )
    assert (
        mu_client.delete(f"/api/admin/users/{member}?confirm=DELETE").status_code == 200
    )
    mu_app.state.settings = mu_app.state.settings.model_copy(
        update={"resend_api_key": "test"}
    )
    assert email_notification_tick(mu_app.state) == 2
    assert {message[0] for message in mu_app.state.mailer.sent} == {"alice@example.com"}


def test_registered_email_change_notifies_both_verified_addresses(
    mu_app, mu_client, member
):
    with Session(mu_app.state.system_engine) as session:
        owner = session.scalar(select(User).where(User.username == "owner"))
        assert owner is not None
        owner.email, owner.email_verified_at = "old@example.com", datetime.now(UTC)
        session.commit()
    assert (
        mu_client.post(
            "/api/account/email", json={"email": "new@example.com"}
        ).status_code
        == 202
    )
    match = re.search(r"\b(\d{6})\b", mu_app.state.mailer.sent[-1][2])
    assert match is not None
    code = match.group(1)
    assert (
        mu_client.post(
            "/api/account/email/verify", json={"email": "new@example.com", "code": code}
        ).status_code
        == 200
    )
    assert {row.recipient for row in notices(mu_app)} == {
        "old@example.com",
        "new@example.com",
    }


def test_verified_registration_queues_welcome_to_registered_address(mu_app, mu_client):
    mu_app.state.settings = mu_app.state.settings.model_copy(
        update={"registration_mode": "open"}
    )
    assert (
        mu_client.post(
            "/api/auth/register",
            json={"email": "new@example.com", "password": "quartz-lantern-42-drift"},
        ).status_code
        == 202
    )
    assert notices(mu_app) == []
    match = re.search(r"\b(\d{6})\b", mu_app.state.mailer.sent[-1][2])
    assert match is not None
    code = match.group(1)
    assert (
        mu_client.post(
            "/api/auth/verify-email", json={"email": "new@example.com", "code": code}
        ).status_code
        == 200
    )
    rows = notices(mu_app)
    assert len(rows) == 1 and rows[0].event == "account_created"
    assert rows[0].recipient == "new@example.com"
