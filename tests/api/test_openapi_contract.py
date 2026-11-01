import json
from pathlib import Path

from fastapi.testclient import TestClient

from resume_tailor_harness.api.app import create_app

CONTRACT = Path("contracts/openapi.json")


def _assert_core_paths(spec):
    paths = spec["paths"]
    for p in (
        "/api/shortlist",
        "/api/pipeline",
        "/api/triage",
        "/api/jobs/{job_id}",
        "/api/discover",
        "/api/reprocess",
        "/api/refresh",
        "/api/runs/{run_id}",
        "/api/runs/{run_id}/events",
        "/api/sources",
        "/api/jobs/company-intelligence-comparisons",
    ):
        assert p in paths, f"missing {p}"


def _assert_scout_source_verification(spec):
    paths = spec["paths"]
    resolve = paths["/api/scout/sessions/{session_id}/proposals/{proposal_id}/resolve"][
        "post"
    ]
    approve = paths["/api/scout/sessions/{session_id}/proposals/{proposal_id}/approve"][
        "post"
    ]
    schemas = spec["components"]["schemas"]

    assert resolve["requestBody"]["required"] is True
    assert resolve["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/ScoutResolveSourceIn")
    assert approve["requestBody"].get("required", False) is False
    approve_variants = approve["requestBody"]["content"]["application/json"]["schema"][
        "anyOf"
    ]
    assert any(
        variant.get("$ref", "").endswith("/ScoutApproveIn")
        for variant in approve_variants
    )
    assert "manualConfirmation" in schemas["ScoutProposalOut"]["properties"]
    assert "resolutionStatus" in schemas["ScoutSourceOut"]["properties"]
    assert "searchedFamilies" in schemas["ScoutSourceOut"]["properties"]
    assert "conflict" in schemas["ScoutProposalOut"]["properties"]["check"]["enum"]


def _assert_company_intelligence_routes(spec):
    paths = spec["paths"]
    resource_path = "/api/jobs/{job_id}/company-intelligence"
    refresh_path = f"{resource_path}/refreshes"
    versions_path = f"{resource_path}/versions"
    assert "get" in paths[resource_path]
    assert "post" not in paths[resource_path]
    assert "post" in paths[refresh_path]
    assert "get" in paths[versions_path]


def _assert_hiring_contacts_routes(spec):
    paths = spec["paths"]
    resource = "/api/jobs/{job_id}/hiring-contact-intelligence"
    assert "get" in paths[resource]
    assert "post" in paths[f"{resource}/refreshes"]
    assert not any("hiring-contact" in path and "send" in path for path in paths)


def _assert_role_preparation_routes(spec):
    paths = spec["paths"]
    resource = "/api/jobs/{job_id}/role-preparation-brief"
    assert "get" in paths[resource]
    assert "post" in paths[f"{resource}/refreshes"]


def _assert_committed_openapi(spec):
    """The committed contract must match the live app — regenerate if this fails."""
    assert CONTRACT.exists(), (
        "run scripts/export_openapi.py and commit contracts/openapi.json"
    )
    committed = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert committed == spec, (
        "contracts/openapi.json is stale — re-run scripts/export_openapi.py"
    )


def test_openapi_contract(tmp_path, subtests):
    app = create_app(
        db_url="sqlite://", data_dir=tmp_path / "data", config_dir=tmp_path / "config"
    )
    spec = app.openapi()
    with TestClient(app) as client:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert response.json() == spec
    for check in (
        _assert_core_paths,
        _assert_scout_source_verification,
        _assert_company_intelligence_routes,
        _assert_hiring_contacts_routes,
        _assert_role_preparation_routes,
        _assert_committed_openapi,
    ):
        with subtests.test(contract=check.__name__):
            check(spec)
