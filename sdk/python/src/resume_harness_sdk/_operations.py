"""Job preparation and durable operation reads using existing guarded routes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal
from urllib.parse import quote

from . import operations
from ._transport import JSON, _Transport, _id, _validated


class OperationAPI(_Transport):
    def create_job(self, body: operations.JobTextInput | Mapping[str, Any]) -> JSON:
        """Add supplied JD text with the complete camelCase request envelope."""
        return self._request("POST", "jobs", json=dict(body)).json()

    def setup_status(self) -> operations.SetupStatus:
        """Read readiness and evidence freshness without changing setup."""
        return _validated(self._request("GET", "setup/status"), operations.SETUP)

    def add_job_url(
        self,
        url: str,
        *,
        company: str | None = None,
        title: str | None = None,
        location: str | None = None,
        allow_browser: bool = True,
        public_extraction: bool = False,
    ) -> JSON:
        """Start URL ingestion; inspect the run result for duplicates or recovery."""
        return self._request(
            "POST",
            "jobs/from-url",
            json={
                "url": url,
                "company": company,
                "title": title,
                "location": location,
                "allowBrowser": allow_browser,
                "publicExtraction": public_extraction,
            },
        ).json()

    def redo_jobs(
        self,
        job_ids: list[int],
        *,
        stages: list[operations.RedoStage],
        deep: bool = False,
        remove_previous_versions: bool = False,
    ) -> JSON:
        """Rerun stages and optionally remove older versions after replacement."""
        if not job_ids or not stages:
            raise ValueError("Provide at least one job ID and stage")
        for job_id in job_ids:
            _id(job_id)
        if any(
            stage not in {"pull", "extract", "tailor", "render"} for stage in stages
        ):
            raise ValueError("stage must be pull, extract, tailor, or render")
        body: dict[str, object] = {
            "jobIds": list(dict.fromkeys(job_ids)),
            "stages": list(dict.fromkeys(stages)),
            "deep": deep,
        }
        if remove_previous_versions:
            if "tailor" not in stages:
                raise ValueError("Removing previous versions requires the tailor stage")
            body["removePreviousVersions"] = True
        return self._request("POST", "redo", json=body).json()

    def get_evidence_portfolio(self, version_id: int) -> operations.EvidencePortfolio:
        """Inspect saved requirement coverage and excerpts; legacy versions may 404."""
        return _validated(
            self._request(
                "GET", f"resume-versions/{_id(version_id)}/evidence-portfolio"
            ),
            operations.PORTFOLIO,
        )

    def list_run_completions(
        self,
        *,
        limit: int = 50,
        unread_only: bool = False,
        surface: Literal["operations", "notifications"] = "operations",
    ) -> list[operations.RunCompletion]:
        """Read durable history; this endpoint returns a list, not a page."""
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit must be an integer from 1 to 100")
        if surface not in {"operations", "notifications"}:
            raise ValueError("surface must be operations or notifications")
        return _validated(
            self._request(
                "GET",
                "run-completions",
                params={"limit": limit, "unread_only": unread_only, "surface": surface},
            ),
            operations.COMPLETIONS,
        )

    def get_run_completion(self, run_id: str) -> operations.RunCompletion:
        """Resolve a completed run even after transient run files expire."""
        return _validated(
            self._request("GET", f"run-completions/by-run/{quote(run_id, safe='')}"),
            operations.COMPLETION,
        )

    def get_run_logs(self, completion_id: int) -> list[operations.OperationLog]:
        """Read retained logs by completion ID, not run ID. Older runs may have none."""
        return _validated(
            self._request("GET", f"run-completions/{_id(completion_id)}/logs"),
            operations.LOGS,
        )
