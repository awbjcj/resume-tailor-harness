import pytest
from sqlmodel import Session

from resume_tailor_harness.tracking.tables import CoverLetter, Job, ResumeVersion


def _login(client):
    response = client.post(
        "/api/auth/login",
        json={"identifier": "owner", "password": "owner-password"},
    )
    assert response.status_code == 200


def test_pat_mint_list_use_and_revoke(mu_client):
    _login(mu_client)
    minted = mu_client.post("/api/account/tokens", json={"name": "automation"})
    assert minted.status_code == 201
    body = minted.json()
    assert body["token"].startswith("rat_")
    listed = mu_client.get("/api/account/tokens").json()["tokens"]
    assert listed[0]["name"] == "automation"
    assert "token" not in listed[0]
    mu_client.cookies.clear()
    assert (
        mu_client.get(
            "/api/pipeline", headers={"Authorization": f"Bearer {body['token']}"}
        ).status_code
        == 200
    )
    _login(mu_client)
    assert mu_client.delete(f"/api/account/tokens/{body['id']}").status_code == 204
    mu_client.cookies.clear()
    assert (
        mu_client.get(
            "/api/pipeline", headers={"Authorization": f"Bearer {body['token']}"}
        ).status_code
        == 401
    )


def test_link_token_is_not_general_query_auth(mu_client):
    _login(mu_client)
    minted = mu_client.post("/api/auth/link-token", json={"purpose": "sse"})
    assert minted.status_code == 200
    token = minted.json()["token"]
    mu_client.cookies.clear()
    assert mu_client.get(f"/api/pipeline?token={token}").status_code == 401


def test_sse_accepts_only_the_owner_purpose_bound_link(mu_app, mu_client):
    _login(mu_client)
    owner_id = mu_app.state.default_context.user_id
    run_id = mu_app.state.run_manager.submit(
        "test", lambda _reporter: {}, user_id=owner_id
    )
    assert mu_app.state.run_manager.get(run_id).user_id == owner_id
    token = mu_client.post("/api/auth/link-token", json={"purpose": "sse"}).json()[
        "token"
    ]
    assert mu_app.state.run_manager.get(run_id).user_id == owner_id
    mu_client.cookies.clear()

    response = mu_client.get(f"/api/runs/{run_id}/events?token={token}")
    assert response.status_code == 200, response.text
    assert '"state": "done"' in response.text

    wrong_purpose = mu_app.state.settings
    from resume_tailor_harness.api.auth import issue_link_token

    download_token = issue_link_token(
        wrong_purpose, user_id=owner_id, purpose="download"
    )
    assert (
        mu_client.get(f"/api/runs/{run_id}/events?token={download_token}").status_code
        == 401
    )


def test_download_link_is_purpose_bound(mu_client):
    _login(mu_client)
    download = mu_client.post(
        "/api/auth/link-token", json={"purpose": "download"}
    ).json()["token"]
    sse = mu_client.post("/api/auth/link-token", json={"purpose": "sse"}).json()[
        "token"
    ]
    mu_client.cookies.clear()

    assert mu_client.get(f"/api/account/export?token={download}").status_code == 200
    assert mu_client.get(f"/api/account/export?token={sse}").status_code == 401


@pytest.mark.parametrize("kind", ["resume-versions", "cover-letters"])
def test_native_pdf_preview_accepts_only_a_download_capability(mu_app, mu_client, kind):
    _login(mu_client)
    context = mu_app.state.default_context
    path = context.paths.root / "output" / "preview.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4 test")
    with Session(context.engine) as session:
        job = Job(source="manual", jd_text="x", company="Acme", title="Engineer")
        session.add(job)
        session.commit()
        session.refresh(job)
        assert job.id is not None
        artifact = (
            ResumeVersion(job_id=job.id, round=0, pdf_path=str(path))
            if kind == "resume-versions"
            else CoverLetter(job_id=job.id, pdf_path=str(path))
        )
        session.add(artifact)
        session.commit()
        session.refresh(artifact)
        artifact_id = artifact.id
    download = mu_client.post(
        "/api/auth/link-token", json={"purpose": "download"}
    ).json()["token"]
    sse = mu_client.post("/api/auth/link-token", json={"purpose": "sse"}).json()[
        "token"
    ]
    mu_client.cookies.clear()
    url = f"/api/{kind}/{artifact_id}/preview"
    assert mu_client.get(url).status_code == 401
    assert mu_client.get(f"{url}?token={sse}").status_code == 401
    response = mu_client.get(f"{url}?token={download}")
    assert response.status_code == 200
    assert response.content == path.read_bytes()
    assert response.headers["content-disposition"].startswith(
        'inline; filename="Acme-Engineer-'
    )
    # The native PDF viewer can issue range requests with the same capability.
    partial = mu_client.get(f"{url}?token={download}", headers={"Range": "bytes=0-7"})
    assert partial.status_code == 206
    assert partial.content == b"%PDF-1.4"


def test_admin_export_accepts_an_admin_download_link(mu_client):
    _login(mu_client)
    token = mu_client.post("/api/auth/link-token", json={"purpose": "download"}).json()[
        "token"
    ]
    mu_client.cookies.clear()

    response = mu_client.get(f"/api/admin/export?token={token}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/gzip"
