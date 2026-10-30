from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlmodel import Session

from resume_harness_sdk import PasswordForm, ResumeHarness
from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.api.schemas.application_accounts import AccountSave
from resume_tailor_harness.services.application_accounts import (
    AccountVault,
    AccountVaultError,
)
from resume_tailor_harness.tracking.tables import Application, Job


@pytest.fixture
def setup(tmp_path):
    app = create_app(
        db_url="sqlite://",
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        env_path=tmp_path / ".env",
    )
    app.state.settings.application_vault_keys = Fernet.generate_key().decode()
    with TestClient(app) as client:
        with Session(app.state.engine) as session:
            session.add_all(
                [
                    Job(
                        source="manual",
                        company="Acme",
                        title="Role one",
                        url="https://acme.wd1.myworkdayjobs.com/jobs/1",
                        status="approved",
                    ),
                    Job(
                        source="manual",
                        company="  ACME ",
                        title="Role two",
                        url="https://acme.wd1.myworkdayjobs.com/jobs/2",
                        status="approved",
                    ),
                    Job(
                        source="manual",
                        company="Different employer",
                        url="https://acme.wd1.myworkdayjobs.com/jobs/3",
                        status="approved",
                    ),
                ]
            )
            session.commit()
        yield app, client


URL = "https://acme.wd1.myworkdayjobs.com/jobs/login"


def enable(client):
    state = client.get("/api/application-accounts").json()
    response = client.patch(
        "/api/application-accounts/policy",
        json={
            "autoRegister": True,
            "revision": state["revision"],
            "userConfirmed": True,
        },
    )
    assert response.status_code == 200, response.text


def prepare(client, job=1, **extra):
    return client.post(
        f"/api/jobs/{job}/application-account/prepare",
        json={"browserUrl": URL, "username": "applicant@example.com", **extra},
    )


def access(client, account, *, job=1, url=URL, operation="secret", **extra):
    return client.post(
        f"/api/jobs/{job}/application-accounts/{account['id']}/{operation}",
        json={"browserUrl": url, "revision": account["revision"], **extra},
    )


def test_registration_is_durable_resumable_and_reused_only_after_authentication(setup):
    app, client = setup
    assert prepare(client).json()["error"]["code"] == "REGISTRATION_DISABLED"
    enable(client)
    first = prepare(client)
    assert first.status_code == 200, first.text
    assert first.json()["action"] == "register"
    account = first.json()["account"]
    assert "password" not in first.text
    secret = access(client, account).json()["password"]
    assert len(secret) == 24
    assert any(c.islower() for c in secret) and any(c.isupper() for c in secret)
    assert any(c.isdigit() for c in secret) and any(c in "!@#$%*-_" for c in secret)
    encrypted = (app.state.data_dir / "application-accounts.vault").read_bytes()
    assert secret.encode() not in encrypted
    assert b"applicant@example.com" not in encrypted
    resumed = prepare(client)
    assert resumed.json() == {"action": "resume_registration", "account": account}
    assert access(client, account).json()["password"] == secret
    pending = access(
        client, account, operation="outcome", outcome="verification_required"
    ).json()
    assert pending["status"] == "pending"
    active = access(
        client, pending, operation="outcome", outcome="authenticated"
    ).json()
    assert active["status"] == "active" and active["lastUsedAt"]
    assert prepare(client, job=2).json() == {"action": "login", "account": active}
    assert access(client, active, job=2).json()["password"] == secret
    assert secret not in client.get("/api/application-accounts").text
    assert secret not in client.get("/api/jobs/2/application-context").text
    assert first.headers["cache-control"] == "no-store"
    assert access(client, active).headers["cache-control"] == "no-store"
    with Session(app.state.engine) as session:
        assert session.get(Application, 1) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://acme.wd1.myworkdayjobs.com/login",
        "https://acme.wd1.myworkdayjobs.com.evil.com/login",
        "https://acme.wd1.myworkdayjobs.com@evil.com/login",
        "https://acme.wd1.myworkdayjobs.com:444/login",
        "https://acme.wd1.myworkdayjobs.com\\@evil.com",
        "https://acme.wd1.myworkdayjobs.com./login",
        "https://evil.com/#https://acme.wd1.myworkdayjobs.com",
        "https://acme.wd1.myworkdayjobs.com\n.evil.com",
    ],
)
def test_untrusted_sites_never_create_or_retrieve_credentials(setup, url):
    _, client = setup
    enable(client)
    account = prepare(client).json()["account"]
    assert access(client, account, url=url).status_code in {403, 422}
    assert prepare(client, browserUrl=url).status_code in {409, 422}
    assert len(client.get("/api/application-accounts").json()["accounts"]) == 1


def test_scope_eligibility_stale_state_failure_and_user_repair(setup):
    app, client = setup
    enable(client)
    account = prepare(client).json()["account"]
    assert access(client, account, job=3).status_code == 403
    assert (
        prepare(client, username="different@example.com").json()["error"]["code"]
        == "ACCOUNT_USERNAME_MISMATCH"
    )
    failed = access(client, account, operation="outcome", outcome="failed").json()
    assert prepare(client).json()["action"] == "needs_attention"
    assert access(client, failed).json()["error"]["code"] == "ACCOUNT_NEEDS_ATTENTION"
    assert access(client, account).json()["error"]["code"] == "ACCOUNT_STALE"
    updated = client.patch(
        f"/api/application-accounts/{account['id']}",
        json={
            "password": "Corrected-secret-1!",
            "revision": failed["revision"],
            "userConfirmed": True,
        },
    )
    assert updated.status_code == 200
    assert access(client, updated.json()).json()["password"] == "Corrected-secret-1!"
    with Session(app.state.engine) as session:
        session.add(Application(job_id=1, status="submitted"))
        session.commit()
    assert (
        access(client, updated.json()).json()["error"]["code"]
        == "APPLICATION_NOT_READY"
    )
    assert prepare(client).status_code == 409
    assert access(client, updated.json(), job=2).status_code == 200


def test_validation_errors_csrf_and_regular_responses_do_not_echo_secrets(setup):
    _, client = setup
    body = {
        "company": "Acme",
        "loginUrl": URL,
        "username": "user",
        "password": "Never-echo-this-1!",
        "userConfirmed": True,
    }
    response = client.post("/api/application-accounts", json={**body, "company": ""})
    assert response.status_code == 422
    assert body["password"] not in response.text
    response = client.post(
        "/api/application-accounts", json={**body, "unexpected": body["password"]}
    )
    assert response.status_code == 422 and body["password"] not in response.text
    response = client.post(
        "/api/application-accounts",
        json=body,
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    client.cookies.set("session", "example")
    assert client.post("/api/application-accounts", json=body).status_code == 403
    response = client.post(
        "/api/application-accounts", json=body, headers={"Origin": "http://testserver"}
    )
    assert response.status_code == 200, response.text
    assert body["password"] not in response.text
    assert "password" not in client.get("/api/application-accounts").text


def test_concurrent_registration_reuses_one_pending_password(setup):
    _, client = setup
    enable(client)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: prepare(client), range(6)))
    assert all(r.status_code == 200 for r in results)
    assert len({r.json()["account"]["id"] for r in results}) == 1
    assert sum(r.json()["action"] == "register" for r in results) == 1
    passwords = {
        access(client, r.json()["account"]).json()["password"] for r in results
    }
    assert len(passwords) == 1


def test_vault_tenant_binding_key_rotation_and_corruption_fail_closed(tmp_path):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    vault = AccountVault(tmp_path, "owner-a", old)
    account = vault.save(
        AccountSave(
            company="Acme",
            login_url=URL,
            username="user",
            password=SecretStr("test-password"),
            user_confirmed=True,
        )
    )
    ciphertext = vault.path.read_bytes()
    for owner, keys in (("owner-b", old), ("owner-a", new)):
        with pytest.raises(AccountVaultError, match="Cannot unlock"):
            AccountVault(tmp_path, owner, keys).status()
        assert vault.path.read_bytes() == ciphertext
    rotated = AccountVault(tmp_path, "owner-a", f"{new},{old}")
    assert rotated.status().accounts[0].id == account.id
    from resume_tailor_harness.api.schemas.application_accounts import (
        AccountPolicyUpdate,
    )

    rotated.policy(
        AccountPolicyUpdate(auto_register=True, revision=1, user_confirmed=True)
    )
    assert AccountVault(tmp_path, "owner-a", new).status().auto_register
    vault.path.write_bytes(b"corrupted")
    with pytest.raises(AccountVaultError):
        rotated.save(
            AccountSave(
                company="Other",
                login_url=URL,
                username="user",
                password=SecretStr("new-secret"),
                user_confirmed=True,
            )
        )
    assert vault.path.read_bytes() == b"corrupted"


def test_oversized_write_preserves_readable_vault(tmp_path, monkeypatch):
    from resume_tailor_harness.api.schemas.application_accounts import AccountUpdate
    from resume_tailor_harness.services import application_accounts

    vault = AccountVault(tmp_path, "owner", Fernet.generate_key().decode())
    account = vault.save(
        AccountSave(
            company="Acme",
            login_url=URL,
            username="user",
            password=SecretStr("original"),
            user_confirmed=True,
        )
    )
    original = vault.path.read_bytes()
    monkeypatch.setattr(
        application_accounts, "_MAX_VAULT_BYTES", len(original) + 1, raising=False
    )
    with pytest.raises(AccountVaultError, match="capacity"):
        vault.update(
            account.id,
            AccountUpdate(
                password=SecretStr("\U0001f512" * 1024),
                revision=1,
                user_confirmed=True,
            ),
        )
    assert vault.path.read_bytes() == original
    assert vault.status().accounts == [account]


def test_unconfigured_vault_and_manual_account_lifecycle(setup):
    app, client = setup
    app.state.settings.application_vault_keys = ""
    assert client.get("/api/application-accounts").json()["configured"] is False
    assert prepare(client).status_code == 503
    app.state.settings.application_vault_keys = Fernet.generate_key().decode()
    body = {
        "company": "Acme",
        "loginUrl": "https://accounts.example.com/login",
        "username": "known",
        "password": "existing-password",
        "userConfirmed": True,
    }
    saved = client.post("/api/application-accounts", json=body)
    assert saved.status_code == 200
    assert (
        client.post("/api/application-accounts", json=body).json()["error"]["code"]
        == "ACCOUNT_EXISTS"
    )
    account = saved.json()
    prepared = prepare(client, browserUrl=body["loginUrl"], username="known")
    assert prepared.json()["action"] == "login"
    assert (
        client.delete(
            f"/api/application-accounts/{account['id']}?revision=999"
        ).status_code
        == 409
    )
    assert (
        client.delete(
            f"/api/application-accounts/{account['id']}?revision=1"
        ).status_code
        == 204
    )
    assert access(client, account, url=body["loginUrl"]).status_code == 404


def test_sdk_fills_login_and_confirmation_without_returning_secret(setup):
    _, client = setup
    enable(client)

    def transport(request):
        response = client.request(
            request.method,
            str(request.url),
            headers=dict(request.headers),
            content=request.content,
        )
        return httpx.Response(
            response.status_code, headers=response.headers, content=response.content
        )

    values = {}
    with ResumeHarness(
        base_url="https://testserver",
        api_key="test",
        transport=httpx.MockTransport(transport),
    ) as sdk:
        result = sdk.prepare_application_account(1, browser_url=URL, username="user")
        form = PasswordForm(
            current_url=lambda: URL,
            is_password=lambda selector: selector in {"password", "confirmation"},
            fill=lambda selector, value: values.update({selector: value}),
            username_selector="username",
            password_selector="password",
            confirmation_selector="confirmation",
        )
        filled = sdk.fill_application_account(1, result["account"], form=form)
        assert values["password"] == values["confirmation"]
        assert values["username"] == "user"
        assert values["password"] not in repr(filled)
        saved = sdk.record_application_account_outcome(
            1, filled, browser_url=URL, outcome="authenticated"
        )
        assert sdk.prepare_application_account(2, browser_url=URL)["account"] == saved
        values.clear()
        login = PasswordForm(
            current_url=lambda: URL,
            is_password=lambda s: s == "password",
            fill=lambda s, v: values.update({s: v}),
            username_selector="username",
            password_selector="password",
        )
        sdk.fill_application_account(2, saved, form=login)
        assert set(values) == {"username", "password"}


def test_disabling_registration_stops_pending_fills_and_preserves_secret(setup):
    _, client = setup
    enable(client)
    account = prepare(client).json()["account"]
    original = access(client, account).json()["password"]
    current = client.get("/api/application-accounts").json()
    response = client.patch(
        "/api/application-accounts/policy",
        json={
            "revision": current["revision"],
            "autoRegister": False,
            "userConfirmed": True,
        },
    )
    assert response.status_code == 200
    assert prepare(client).json()["error"]["code"] == "REGISTRATION_DISABLED"
    assert access(client, account).json()["error"]["code"] == "REGISTRATION_DISABLED"
    enable(client)
    assert access(client, account).json()["password"] == original


def test_hosted_auth_and_tenant_isolation(mu_app, mu_client):
    from sqlalchemy.orm import Session as SystemSession
    from resume_tailor_harness.api.auth import hash_password
    from resume_tailor_harness.tenancy.system_db import User
    from resume_tailor_harness.tenancy.workspace import provision_workspace

    mu_app.state.settings.application_vault_keys = Fernet.generate_key().decode()
    assert mu_client.get("/api/application-accounts").status_code == 401
    assert (
        mu_client.post(
            "/api/jobs/1/application-accounts/unknown/secret",
            json={"browserUrl": URL, "revision": 1},
        ).status_code
        == 401
    )
    mu_client.post(
        "/api/auth/login", json={"identifier": "owner", "password": "owner-password"}
    )
    token = mu_client.post("/api/account/tokens", json={"name": "vault"}).json()[
        "token"
    ]
    mu_client.cookies.clear()
    auth = {"Authorization": f"Bearer {token}"}
    body = {
        "company": "Acme",
        "loginUrl": URL,
        "username": "owner-private",
        "password": "owner-secret",
        "userConfirmed": True,
    }
    saved = mu_client.post("/api/application-accounts", json=body, headers=auth)
    assert saved.status_code == 200, saved.text
    with SystemSession(mu_app.state.system_engine) as session:
        session.add(
            User(
                id="vault-second",
                username="second",
                password_hash=hash_password("second-password", iterations=1000),
            )
        )
        session.commit()
    provision_workspace(
        mu_app.state.data_dir,
        "vault-second",
        template_dir=mu_app.state.template_config_dir,
    )
    mu_client.post(
        "/api/auth/login", json={"identifier": "second", "password": "second-password"}
    )
    assert mu_client.get("/api/application-accounts").json()["accounts"] == []
    account_id = saved.json()["id"]
    assert (
        mu_client.delete(
            f"/api/application-accounts/{account_id}?revision=1",
            headers={"Origin": "https://testserver"},
        ).status_code
        == 404
    )
    assert (
        mu_client.patch(
            f"/api/application-accounts/{account_id}",
            json={
                "revision": 1,
                "password": "attacker-password",
                "userConfirmed": True,
            },
            headers={"Origin": "https://testserver"},
        ).status_code
        == 404
    )
    mu_client.cookies.clear()
    assert (
        mu_client.get("/api/application-accounts", headers=auth).json()["accounts"][0][
            "username"
        ]
        == "owner-private"
    )
