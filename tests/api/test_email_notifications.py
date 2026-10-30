import re
from datetime import datetime, timedelta, timezone

from sqlmodel import Session

from resume_tailor_harness.api.auth import hash_password
from resume_tailor_harness.mail.tables import EmailNotificationPreference as Preference
from resume_tailor_harness.tenancy.system_db import User
from resume_tailor_harness.tenancy.bootstrap import build_context
from resume_tailor_harness.tracking.tables import Job
from resume_tailor_harness.services.email_notification_scheduler import (
    email_notification_tick,
)


def login(client, name="owner"):
    assert (
        client.post(
            "/api/auth/login", json={"identifier": name, "password": "owner-password"}
        ).status_code
        == 200
    )


def test_guard_validation_and_tenant_isolation(mu_app, mu_client):
    assert mu_client.get("/api/email-notifications").status_code == 401
    login(mu_client)
    assert (
        mu_client.put(
            "/api/email-notifications", json={"email": "bad", "enabled": True}
        ).status_code
        == 422
    )
    assert (
        mu_client.put(
            "/api/email-notifications",
            json={
                "email": "a@example.com",
                "enabled": True,
                "pendingReviews": False,
                "statistics": False,
                "reminders": False,
            },
        ).status_code
        == 422
    )
    saved = mu_client.put(
        "/api/email-notifications", json={"email": "OWNER@example.com", "enabled": True}
    )
    assert saved.status_code == 200
    assert saved.json()["email"] == "owner@example.com"
    assert saved.json()["verifiedAt"] is None
    assert "codeHash" not in saved.json() and "unsubscribeToken" not in saved.json()
    with Session(mu_app.state.system_engine) as session:
        session.add(
            User(
                id="other",
                username="other",
                password_hash=hash_password("owner-password", iterations=1000),
            )
        )
        session.commit()
    mu_client.cookies.clear()
    login(mu_client, "other")
    assert mu_client.get("/api/email-notifications").json()["email"] == ""


def test_verified_subscription_and_public_unsubscribe_are_separate_from_account_mail(
    mu_app, mu_client
):
    # Replace only test configuration; the injected mailbox never hits a network.
    mu_app.state.settings = mu_app.state.settings.model_copy(
        update={
            "mail_from": "sender@example.com",
            "resend_api_key": "test",
            "app_base_url": "https://testserver",
        }
    )
    login(mu_client)
    mu_client.put(
        "/api/email-notifications",
        json={"email": "different@example.com", "enabled": True, "frequency": "weekly"},
    )
    assert mu_client.post("/api/email-notifications/verification").status_code == 200
    match = re.search(r"\b(\d{6})\b", mu_app.state.mailer.sent[-1][2])
    assert match is not None
    code = match[1]
    response = mu_client.post(
        "/api/email-notifications/verify",
        json={"email": "different@example.com", "code": code},
    )
    assert response.status_code == 200
    assert response.json()["verifiedAt"] and response.json()["nextSendAt"]
    with Session(mu_app.state.engine) as session:
        preference = session.get(Preference, 1)
        assert preference is not None
        token = preference.unsubscribe_token
    user_id = mu_app.state.default_context.user_id
    mu_client.cookies.clear()
    url = f"/api/email-notifications/unsubscribe/{user_id}/{token}"
    assert mu_client.get(url).status_code == 200
    with Session(mu_app.state.engine) as session:
        preference = session.get(Preference, 1)
        assert preference is not None
        assert preference.enabled is True
    assert (
        mu_client.post(url, data={"List-Unsubscribe": "One-Click"}).status_code == 200
    )
    assert mu_client.post(url).status_code == 200
    assert (
        mu_client.post(
            f"/api/email-notifications/unsubscribe/{user_id}/wrong"
        ).status_code
        == 404
    )
    login(mu_client)
    assert mu_client.get("/api/email-notifications").json()["enabled"] is False
    with Session(mu_app.state.system_engine) as session:
        user = session.get(User, user_id)
        assert user is not None
        assert user.email is None  # notification email never changes login identity


def test_unconfigured_delivery_reports_unavailable_but_allows_opt_out(
    mu_app, mu_client
):
    login(mu_client)
    result = mu_client.put(
        "/api/email-notifications", json={"email": "user@example.com", "enabled": True}
    )

    assert result.json()["deliveryAvailable"] is False
    assert mu_client.post("/api/email-notifications/verification").status_code == 503
    assert (
        mu_client.put(
            "/api/email-notifications",
            json={"email": "user@example.com", "enabled": False},
        ).status_code
        == 200
    )


def test_scheduler_isolates_recipients_skips_disabled_accounts_and_respects_local_mode(
    mu_app, mu_client
):
    moment = datetime.now(timezone.utc)
    state = mu_app.state
    state.settings = state.settings.model_copy(
        update={
            "mail_from": "sender@example.com",
            "resend_api_key": "test",
            "app_base_url": "https://testserver",
        }
    )
    contexts = {}
    with Session(state.system_engine) as session:
        owner = session.get(User, state.default_context.user_id)
        assert owner is not None
        users = [owner]
        for name in ("second", "disabled"):
            user = User(
                id=name,
                username=name,
                password_hash="unused",
                disabled_at=moment if name == "disabled" else None,
            )
            session.add(user)
            users.append(user)
        session.commit()
        for user in users:
            context = build_context(
                user,
                state.data_dir,
                state.settings,
                state.engine_registry,
                system_engine=state.system_engine,
                template_dir=state.template_config_dir,
            )
            contexts[user.username] = context
            with Session(context.engine) as workspace:
                workspace.add(
                    Preference(
                        email=f"{user.username}@example.com",
                        enabled=True,
                        verified_at=moment,
                        next_send_at=moment - timedelta(minutes=1),
                        unsubscribe_token=f"test-{user.id}",
                    )
                )
                workspace.add(
                    Job(
                        source="test",
                        title=f"Private {user.username} job",
                        status="shortlisted",
                    )
                )
                workspace.commit()
    assert email_notification_tick(state) == 2
    delivered = state.mailer.sent
    assert {item[0] for item in delivered} == {
        "owner@example.com",
        "second@example.com",
    }
    for recipient, _, body in delivered:
        name = recipient.split("@")[0]
        assert f"Private {name} job" in body
        assert "Private disabled job" not in body
        assert (
            "Private second job" if name == "owner" else "Private owner job"
        ) not in body
    state.mailer.sent.clear()
    for context in contexts.values():
        with Session(context.engine) as workspace:
            row = workspace.get(Preference, 1)
            assert row is not None
            row.next_send_at = moment - timedelta(minutes=1)
            workspace.add(row)
            workspace.commit()
    state.app_mode = "local"
    assert email_notification_tick(state) == 1
    assert state.mailer.sent[0][0] == "owner@example.com"


def test_cooldown_does_not_consume_send_allowance(mu_app, mu_client):
    mu_app.state.settings = mu_app.state.settings.model_copy(
        update={
            "mail_from": "sender@example.com",
            "resend_api_key": "test",
            "app_base_url": "https://testserver",
        }
    )
    login(mu_client)
    mu_client.put(
        "/api/email-notifications", json={"email": "me@example.com", "enabled": True}
    )
    endpoint = "/api/email-notifications/verification"
    assert mu_client.post(endpoint).status_code == 200
    for _ in range(2):
        assert mu_client.post(endpoint).status_code == 429
    for _ in range(2):
        with Session(mu_app.state.engine) as session:
            row = session.get(Preference, 1)
            assert row is not None
            row.code_sent_at = datetime.now(timezone.utc) - timedelta(minutes=2)
            session.add(row)
            session.commit()
        assert mu_client.post(endpoint).status_code == 200
    assert len(mu_app.state.mailer.sent) == 3
    assert mu_client.post(endpoint).status_code == 429


def test_cooldown_requests_still_consume_abuse_budget(mu_app, mu_client):
    from resume_tailor_harness.api import attempts

    mu_app.state.settings = mu_app.state.settings.model_copy(
        update={
            "mail_from": "sender@example.com",
            "resend_api_key": "test",
            "app_base_url": "https://testserver",
        }
    )
    login(mu_client)
    mu_client.put(
        "/api/email-notifications", json={"email": "me@example.com", "enabled": True}
    )
    for _ in range(10):
        mu_client.post("/api/email-notifications/verification")
    assert not attempts.consume(
        mu_app.state.system_engine,
        email="notification:me@example.com",
        ip="testclient",
        scopes=attempts.DEFAULT_SCOPES,
    )
    assert len(mu_app.state.mailer.sent) == 1
