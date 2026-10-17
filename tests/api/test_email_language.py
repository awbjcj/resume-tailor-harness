import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from resume_tailor_harness.api.auth import hash_password
from resume_tailor_harness.mail.account_notifications import (
    deliver_account_emails,
    enqueue_account_email,
    EVENTS,
)
from resume_tailor_harness.mail.localization import ZH, detail_value, translate
from resume_tailor_harness.mail.tables import EmailNotificationPreference
from resume_tailor_harness.services.email_notification_scheduler import (
    email_notification_tick,
)
from resume_tailor_harness.services import email_notifications
from resume_tailor_harness.tenancy.system_db import User
from resume_tailor_harness.tenancy.workspace import provision_workspace


class Mailbox:
    def __init__(self):
        self.sent = []

    def send(self, **message):
        self.sent.append(message)

    def notify(self, **message):
        self.send(**message)


def login(client, username="owner", password="owner-password"):
    assert (
        client.post(
            "/api/auth/login", json={"identifier": username, "password": password}
        ).status_code
        == 200
    )


def test_dashboard_language_is_validated_saved_and_tenant_scoped(mu_app, mu_client):
    path = "/api/config/language"
    assert mu_client.put(path, json={"language": "zh-CN"}).status_code == 401
    login(mu_client)
    assert mu_client.put(path, json={"language": "fr"}).status_code == 422
    assert mu_client.put(path, json={"language": "zh-CN"}).status_code == 200
    assert mu_client.get(path).json() == {"language": "zh-CN"}
    with Session(mu_app.state.system_engine) as session:
        assert (
            session.get(User, mu_app.state.default_context.user_id).dashboard_language
            == "zh-CN"
        )
        session.add(
            User(
                id="other",
                username="other",
                password_hash=hash_password("other-password"),
            )
        )
        session.commit()
    provision_workspace(
        mu_app.state.data_dir, "other", template_dir=mu_app.state.template_config_dir
    )
    mu_client.cookies.clear()
    login(mu_client, "other", "other-password")
    assert mu_client.get(path).json() == {"language": "en"}


def test_saved_language_reaches_verification_and_scheduled_digest(
    mu_app, mu_client, monkeypatch
):
    login(mu_client)
    mu_app.state.settings = mu_app.state.settings.model_copy(
        update={"resend_api_key": "test", "app_base_url": "https://app.example.com"}
    )
    mu_app.state.mailer = mailbox = Mailbox()
    mu_client.put("/api/config/language", json={"language": "zh-CN"})
    assert (
        mu_client.put(
            "/api/email-notifications",
            json={"email": "notify@example.com", "enabled": True, "frequency": "daily"},
        ).status_code
        == 200
    )
    assert mu_client.post("/api/email-notifications/verification").status_code == 200
    verification = mailbox.sent[-1]
    assert verification["subject"] == "验证接收通知的邮箱"
    assert 'lang="zh-CN"' in verification["html"]
    assert "设置 → 邮件通知" in verification["html"]
    code = re.search(r"\b\d{6}\b", verification["body"])[0]
    assert (
        mu_client.post(
            "/api/email-notifications/verify",
            json={"email": "notify@example.com", "code": code},
        ).status_code
        == 200
    )
    monkeypatch.setattr(
        email_notifications, "now_utc", lambda: datetime.now(UTC) + timedelta(days=2)
    )
    assert email_notification_tick(mu_app.state) >= 1
    digest = mailbox.sent[-1]
    assert digest["subject"] == "求职进展摘要"
    assert 'lang="zh-CN"' in digest["html"]
    assert "求职统计" in digest["body"]
    assert "applications submitted" not in digest["body"]
    assert "每日摘要" in digest["body"]
    mu_client.put("/api/config/language", json={"language": "en"})
    monkeypatch.setattr(
        email_notifications, "now_utc", lambda: datetime.now(UTC) + timedelta(days=4)
    )
    assert email_notification_tick(mu_app.state) >= 1
    assert mailbox.sent[-1]["subject"] == "Your job-search digest"
    assert 'lang="en"' in mailbox.sent[-1]["html"]


def test_password_reset_uses_saved_dashboard_language(mu_app, mu_client):
    login(mu_client)
    mu_client.put("/api/config/language", json={"language": "zh-CN"})
    with Session(mu_app.state.system_engine) as session:
        owner = session.get(User, mu_app.state.default_context.user_id)
        owner.email, owner.email_verified_at = "owner@example.com", datetime.now(UTC)
        session.commit()
    mu_app.state.mailer = mailbox = Mailbox()
    assert (
        mu_client.post(
            "/api/auth/password/forgot",
            json={"email": "owner@example.com"},
            headers={"Accept-Language": "en"},
        ).status_code
        == 202
    )
    assert "密码重置验证码" in mailbox.sent[-1]["subject"]
    assert "15 分钟内有效" in mailbox.sent[-1]["body"]


def test_account_notices_use_recipient_language_and_keep_it_after_deletion(
    mu_app, mu_client
):
    login(mu_client)
    mu_client.put("/api/config/language", json={"language": "zh-CN"})
    owner_id = mu_app.state.default_context.user_id
    with Session(mu_app.state.system_engine) as session:
        user = session.get(User, owner_id)
        user.email, user.email_verified_at = "owner@example.com", datetime.now(UTC)
        enqueue_account_email(
            session,
            user,
            "account_updated",
            {"Role": "Administrator → Member", "Reason": "Keep this exact reason"},
        )
        session.commit()
    mailbox = Mailbox()
    settings = mu_app.state.settings.model_copy(update={"resend_api_key": "test"})
    assert deliver_account_emails(mu_app.state.system_engine, mailbox, settings) == 1
    assert mailbox.sent[-1]["subject"].startswith("账户设置已更新")
    assert "管理员 → 成员" in mailbox.sent[-1]["body"]
    assert "Keep this exact reason" in mailbox.sent[-1]["html"]
    with Session(mu_app.state.system_engine) as session:
        user = session.get(User, owner_id)
        enqueue_account_email(session, user, "account_deleted")
        session.delete(user)
        session.commit()
    assert deliver_account_emails(mu_app.state.system_engine, mailbox, settings) == 1
    assert mailbox.sent[-1]["subject"].startswith("账户已删除")
    assert 'lang="zh-CN"' in mailbox.sent[-1]["html"]


def test_all_account_event_titles_and_explanations_have_chinese_copy():
    for title, summary in EVENTS.values():
        assert title in ZH, title
        assert summary in ZH, summary


@pytest.mark.parametrize(
    "label,value,expected",
    [
        ("Shared-key access", "Granted → Revoked", "已授权 → 已撤销"),
        ("Concurrent run limit", "System default → 0", "系统默认值 → 不限制"),
        ("Active job limit", "Unlimited → 10", "不限制 → 10"),
        ("Cancel at end of term", "Yes", "是"),
        ("Available for new assignments", "No", "否"),
        ("Renewal cycle", "1 month", "每月"),
        ("Renewal cycle", "3 month", "每 3 个月"),
        ("Renewal cycle", "2 week", "每 2 周"),
        ("Quota tier", "FREE", "免费档位"),
        ("Quota tier", "My Custom Tier", "My Custom Tier"),
        ("Reason", "Member → Administrator", "Member → Administrator"),
        ("Token name", "Granted", "Granted"),
        ("New registered email", "member@example.com", "member@example.com"),
    ],
)
def test_account_details_translate_system_values_and_preserve_user_text(
    label, value, expected
):
    assert translate(label, "zh-CN") != label
    assert detail_value(label, value, "zh-CN") == expected
    assert detail_value(label, value, "en") == value


def test_queued_notice_uses_latest_dashboard_language_at_first_delivery(
    mu_app, mu_client
):
    login(mu_client)
    owner_id = mu_app.state.default_context.user_id
    settings = mu_app.state.settings.model_copy(update={"resend_api_key": "test"})
    mailbox = Mailbox()
    for selected, expected in [
        ("zh-CN", "账户设置已更新"),
        ("en", "Your account was updated"),
    ]:
        with Session(mu_app.state.system_engine) as session:
            user = session.get(User, owner_id)
            user.email, user.email_verified_at = "owner@example.com", datetime.now(UTC)
            enqueue_account_email(session, user, "account_updated")
            session.commit()
        assert (
            mu_client.put(
                "/api/config/language", json={"language": selected}
            ).status_code
            == 200
        )
        assert (
            deliver_account_emails(mu_app.state.system_engine, mailbox, settings) == 1
        )
        assert mailbox.sent[-1]["subject"].startswith(expected)
        assert f'lang="{selected}"' in mailbox.sent[-1]["html"]


def test_unsubscribe_page_uses_dashboard_language_and_get_keeps_consent(
    mu_app, mu_client
):
    login(mu_client)
    mu_client.put("/api/config/language", json={"language": "zh-CN"})
    with Session(mu_app.state.engine) as session:
        session.add(
            EmailNotificationPreference(
                email="digest@example.com",
                enabled=True,
                unsubscribe_token="unsubscribe-test-token",
            )
        )
        session.commit()
    owner_id = mu_app.state.default_context.user_id
    mu_client.cookies.clear()
    url = f"/api/email-notifications/unsubscribe/{owner_id}/unsubscribe-test-token"
    confirmation = mu_client.get(url)
    assert confirmation.status_code == 200
    assert 'lang="zh-CN"' in confirmation.text
    assert "关闭求职摘要邮件？" in confirmation.text
    assert "账户和安全通知" in confirmation.text
    with Session(mu_app.state.engine) as session:
        assert session.get(EmailNotificationPreference, 1).enabled is True
    response = mu_client.post(url)
    assert response.status_code == 200 and "求职摘要邮件已关闭" in response.text
