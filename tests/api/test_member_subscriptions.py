from sqlalchemy.orm import Session

from resume_tailor_harness.api.auth import hash_password
from resume_tailor_harness.tenancy.system_db import User


def test_admin_subscription_grant_renew_revoke_and_member_visibility(mu_app, mu_client):
    with Session(mu_app.state.system_engine) as session:
        session.add(
            User(
                id="alice0000000",
                username="alice",
                role="user",
                password_hash=hash_password("member-password"),
            )
        )
        session.commit()
    mu_client.post(
        "/api/auth/login", json={"identifier": "owner", "password": "owner-password"}
    )
    endpoint = "/api/admin/quota-accounts/alice0000000/subscription"
    payload = {
        "action": "ACTIVATE",
        "tierId": "SUBSCRIBER",
        "cycles": 1,
        "reason": "invoice paid",
        "idempotencyKey": "invoice-12345",
    }
    response = mu_client.post(endpoint, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ACTIVE"
    assert response.json()["expiresAt"].endswith("Z")
    assert mu_client.post(endpoint, json=payload).json() == response.json()
    conflict = mu_client.post(endpoint, json={**payload, "cycles": 2})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    ledger = mu_client.get("/api/admin/quota-accounts/alice0000000/ledger").json()[
        "data"
    ]
    assert sum(row["kind"] == "SUBSCRIPTION_ACTIVATED" for row in ledger) == 1
    mu_client.post(
        "/api/auth/login", json={"identifier": "alice", "password": "member-password"}
    )
    assert mu_client.post(endpoint, json=payload).status_code == 403
    usage = mu_client.get("/api/account/usage")
    assert usage.status_code == 200, usage.text
    assert usage.json()["quota"]["subscriptionStatus"] == "ACTIVE"
    assert usage.json()["quota"]["enforcementStatus"] == "ACTIVE"
    mu_client.post(
        "/api/auth/login", json={"identifier": "owner", "password": "owner-password"}
    )
    revoked = mu_client.post(
        endpoint, json={**payload, "action": "REVOKE", "idempotencyKey": "revoke-12345"}
    )
    assert revoked.status_code == 200
    account = mu_client.get("/api/admin/quota-accounts/alice0000000").json()
    assert account["tierId"] == "FREE"
    assert account["subscriptionStatus"] == "REVOKED"


def test_subscription_validation_and_missing_member(mu_client):
    mu_client.post(
        "/api/auth/login", json={"identifier": "owner", "password": "owner-password"}
    )
    endpoint = "/api/admin/quota-accounts/missing/subscription"
    payload = {
        "action": "ACTIVATE",
        "tierId": "SUBSCRIBER",
        "reason": "invoice paid",
        "idempotencyKey": "invoice-12345",
    }
    assert mu_client.post(endpoint, json=payload).status_code == 404
    assert mu_client.post(endpoint, json={**payload, "cycles": 0}).status_code == 422
    assert mu_client.post(endpoint, json={**payload, "reason": " "}).status_code == 409


def test_hosted_enforcement_survives_settings_refresh(mu_app):
    from resume_tailor_harness.api.deps import refresh_platform_settings
    from resume_tailor_harness.config import Settings

    assert mu_app.state.settings.cost_quota_enforcement == "enforce"
    refresh_platform_settings(mu_app, Settings(_env_file=None))
    assert mu_app.state.settings.cost_quota_enforcement == "enforce"
    refresh_platform_settings(mu_app, Settings(_env_file=None, cost_quota_enforcement="shadow"))
    assert mu_app.state.settings.cost_quota_enforcement == "shadow"
