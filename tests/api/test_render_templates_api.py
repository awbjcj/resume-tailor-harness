"""Custom templates are validated, sandboxed, previewable, and deletable."""

import pytest
from fastapi.testclient import TestClient

from resume_tailor_harness.api.app import create_app


VALID_TYP = b"""
#let payload = json(bytes(sys.inputs.at("data", default: "{}")))
#let zoom = float(sys.inputs.at("zoom", default: "1.0"))
#set text(size: 10pt * zoom)
= #payload.at("contact").at("name")
#payload.at("summary", default: "")
"""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(db_url="sqlite://", config_dir=tmp_path / "config")
    with TestClient(app) as test_client:
        yield test_client


def _upload(client, name="mine.typ", body=VALID_TYP):
    return client.post(
        "/api/config/render/templates",
        files={"file": (name, body, "text/plain")},
    )


def test_bundled_templates_list_select_and_preview(client, subtests) -> None:
    response = client.get("/api/config/render/templates")
    assert response.status_code == 200
    assert response.json()[0]["id"] == "classic"
    assert response.json()[0]["kind"] == "bundled"
    assert len(response.json()) == 8

    for template_id in (
        "classic",
        "modern",
        "technical",
        "executive",
        "graduate",
        "academic",
        "minimal",
        "compact",
    ):
        with subtests.test(template=template_id):
            selected = client.put(
                "/api/config/render", json={"template": template_id, "fitOnePage": True}
            )
            assert selected.status_code == 200
            preview = client.get(f"/api/config/render/templates/{template_id}/preview")
            assert preview.status_code == 200, preview.text
            assert preview.content.startswith(b"%PDF")


def test_custom_template_upload_preview_invalid_replacement_and_delete(client) -> None:
    uploaded = _upload(client)
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["id"] == "custom:mine"
    assert "custom:mine" in {
        item["id"] for item in client.get("/api/config/render/templates").json()
    }
    preview = client.get("/api/config/render/templates/custom:mine/preview")
    assert preview.status_code == 200, preview.text
    assert preview.headers["content-type"] == "application/pdf"
    assert preview.content.startswith(b"%PDF")

    invalid = _upload(client, body=b"#broken(")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "template_invalid"
    assert (
        client.get("/api/config/render/templates/custom:mine/preview").status_code
        == 200
    )

    selected = client.put(
        "/api/config/render",
        json={"template": "custom:mine", "fitOnePage": True},
    )
    assert selected.status_code == 200, selected.text
    deleted = client.delete("/api/config/render/templates/mine")
    assert deleted.status_code == 204
    assert client.get("/api/config/render").json()["template"] == "classic"


def test_invalid_template_requests_use_standard_errors(client, subtests) -> None:
    for name in ("mine.txt", "../mine.typ", "a.b.typ"):
        with subtests.test(upload_name=name):
            response = _upload(client, name=name)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "template_invalid"

    with subtests.test(msg="oversized upload"):
        response = _upload(client, body=b"x" * (200 * 1024 + 1))
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "template_invalid"

    with subtests.test(msg="missing preview"):
        missing = client.get("/api/config/render/templates/custom:ghost/preview")
        assert missing.status_code == 422
        assert missing.json()["error"]["code"] == "template_not_found"

    for encoded_stem in ("%2E%2E", "a.b"):
        with subtests.test(delete_stem=encoded_stem):
            response = client.delete(f"/api/config/render/templates/{encoded_stem}")
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "template_not_found"

    assert len(client.get("/api/config/render/templates").json()) == 8
