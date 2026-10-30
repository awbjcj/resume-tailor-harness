from sqlmodel import Session, SQLModel, create_engine

from resume_tailor_harness.services import discovery
from resume_tailor_harness.discovery.connectors.runner import PullReport
from resume_tailor_harness.discovery.scraper.dashboard import DashboardScraper
from resume_tailor_harness.discovery.search_config import SearchConfig


def _session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_pull_jobs_passes_source_ids_to_per_entry_build(monkeypatch):
    captured = {}

    def fake_build(config, settings, source_ids=None):
        captured["source_ids"] = source_ids
        return []

    monkeypatch.setattr(discovery, "build_source_connectors", fake_build)
    monkeypatch.setattr(discovery, "load_search_config", lambda path: object())
    monkeypatch.setattr(discovery, "load_connectors_config", lambda path: object())
    with _session() as session:
        discovery.pull_jobs(session, source_ids=["greenhouse:anthropic"])

    assert captured["source_ids"] == ["greenhouse:anthropic"]


def test_public_board_jobs_are_included_in_refresh_discovery_scope(monkeypatch):
    from resume_tailor_harness.discovery.scraper.contracts import (
        Draft,
        PullReport as ScrapePullReport,
    )
    from resume_tailor_harness.discovery.scraper.tables import ScrapeSourceRow
    from resume_tailor_harness.services import scrape_review

    monkeypatch.setattr(discovery, "load_search_config", lambda path: SearchConfig())
    monkeypatch.setattr(discovery, "load_connectors_config", lambda path: object())
    monkeypatch.setattr(discovery, "build_source_connectors", lambda *a, **kw: [])
    monkeypatch.setattr(discovery, "run_pull", lambda *a, **kw: PullReport())
    monkeypatch.setattr(
        scrape_review,
        "pull_source",
        lambda *a, **kw: ScrapePullReport(imported=2, changed_raw_job_ids=[41, 42]),
    )
    with _session() as session:
        draft = Draft(source_id="public-board", url="https://example.com/jobs")
        session.add(
            ScrapeSourceRow(
                id="public-board", url=draft.url, payload=draft.model_dump_json()
            )
        )
        session.commit()
        report = discovery.pull_jobs(session)
        assert report.changed_raw_job_ids == [41, 42]


def test_pull_jobs_forwards_skip_known(monkeypatch):
    captured = {}

    def fake_run_pull(session, connectors, search, telemetry_path, **kwargs):
        captured.update(kwargs)
        from resume_tailor_harness.discovery.connectors.runner import PullReport

        return PullReport()

    monkeypatch.setattr(discovery, "run_pull", fake_run_pull)
    monkeypatch.setattr(
        discovery, "build_source_connectors", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(discovery, "load_search_config", lambda path: object())
    monkeypatch.setattr(discovery, "load_connectors_config", lambda path: object())
    with _session() as session:
        discovery.pull_jobs(session, skip_known=False)

    assert captured["skip_known"] is False


def test_pull_jobs_does_not_replay_unreviewed_host_recipes(monkeypatch):
    scraper = DashboardScraper([])
    observed = {}

    monkeypatch.setattr(discovery, "load_search_config", lambda path: SearchConfig())
    monkeypatch.setattr(discovery, "load_connectors_config", lambda path: object())
    monkeypatch.setattr(
        discovery, "build_source_connectors", lambda *args, **kwargs: [scraper]
    )

    def fake_run_pull(session, connectors, search, telemetry_path, **kwargs):
        observed["connectors"] = connectors
        return PullReport()

    monkeypatch.setattr(discovery, "run_pull", fake_run_pull)

    with _session() as session:
        discovery.pull_jobs(session, relearn=True)

    assert observed["connectors"] == []
