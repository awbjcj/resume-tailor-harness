import io
import json
import tarfile


def _login(client):
    response = client.post(
        "/api/auth/login",
        json={"identifier": "owner", "password": "owner-password"},
    )
    assert response.status_code == 200


def _bundle(sections: list[str], files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        blob = json.dumps(
            {"version": 1, "exportedAt": "", "sections": sections}
        ).encode("utf-8")
        info = tarfile.TarInfo("manifest.json")
        info.size = len(blob)
        tar.addfile(info, io.BytesIO(blob))
        for name, text in files.items():
            payload = text.encode("utf-8")
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            tar.addfile(member, io.BytesIO(payload))
    return buffer.getvalue()


def test_settings_bundle_preview_import_and_reset_lifecycle(mu_client):
    assert mu_client.get("/api/settings/sections").status_code == 401
    _login(mu_client)
    response = mu_client.get("/api/settings/sections")
    assert response.status_code == 200
    body = response.json()
    ids = [section["id"] for section in body["sections"]]
    assert len(ids) == 14
    assert "application_profile" in ids
    assert "sources" in ids
    assert all("customized" in section for section in body["sections"])

    response = mu_client.get("/api/settings/bundle")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/gzip"

    sections_before = mu_client.get("/api/settings/sections").json()
    response = mu_client.post(
        "/api/settings/bundle/preview",
        files={
            "file": (
                "b.tar.gz",
                _bundle(["sources"], {"config/connectors.yaml": "companies: []\n"}),
                "application/gzip",
            )
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert [section["id"] for section in body["sections"]] == ["sources"]
    assert body["unknownSections"] == []
    assert mu_client.get("/api/settings/sections").json() == sections_before

    response = mu_client.post(
        "/api/settings/bundle?confirm=APPLY",
        files={
            "file": (
                "b.tar.gz",
                _bundle(
                    ["sources"], {"config/connectors.yaml": "companies:\n  urls: []\n"}
                ),
                "application/gzip",
            )
        },
    )
    assert response.status_code == 200
    assert response.json()["applied"] == ["sources"]

    response = mu_client.post("/api/settings/sections/sources/reset")
    assert response.status_code == 200
    assert response.json() == {
        "id": "sources",
        "label": "Company sources",
        "customized": False,
    }


def test_settings_bundle_errors_leave_sections_unchanged(mu_client, subtests):
    _login(mu_client)
    sections_before = mu_client.get("/api/settings/sections").json()
    for route, payload, code in (
        ("/api/settings/bundle", _bundle([], {}), "CONFIRM_REQUIRED"),
        ("/api/settings/bundle?confirm=APPLY", b"not gzip", "INVALID_BUNDLE"),
    ):
        with subtests.test(code=code):
            response = mu_client.post(
                route,
                files={"file": ("b.tar.gz", payload, "application/gzip")},
            )
            assert response.status_code == 400
            assert response.json()["error"]["code"] == code

    with subtests.test(msg="unknown section"):
        response = mu_client.post("/api/settings/sections/nope/reset")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    assert mu_client.get("/api/settings/sections").json() == sections_before


def test_reset_is_refused_while_runs_are_active(mu_client, mu_app, monkeypatch):
    _login(mu_client)
    monkeypatch.setattr(
        mu_app.state.run_manager, "list_active", lambda user_id=None: ["run-1"]
    )
    response = mu_client.post("/api/settings/sections/sources/reset")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RUNS_ACTIVE"
