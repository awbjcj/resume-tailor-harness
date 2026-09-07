from sqlmodel import Session, select
from resume_tailor_harness.db import make_engine, init_db
from resume_tailor_harness.discovery.scraper.store import ScrapeStore
from resume_tailor_harness.discovery.scraper.contracts import (
    Draft,
    BoardPlan,
    ValidationResult,
)


def test_export_import_requires_destination_revalidation():
    from resume_tailor_harness.services.scrape_transfer import (
        export_sources,
        import_sources,
    )

    engine = make_engine("sqlite://")
    other = make_engine("sqlite://")
    init_db(engine)
    init_db(other)
    with Session(engine) as session:
        draft = Draft(
            source_id="one",
            url="https://example.com/jobs",
            state="validated",
            validation=ValidationResult(valid=True),
            plan=BoardPlan(
                card_selector="article", link_selector="a", detail_selector=".jd"
            ),
        )
        store = ScrapeStore(session)
        store.save_draft(draft)
        store.approve(draft.id, 0)
        session.commit()
        payload = export_sources(session)
        assert "samples" not in payload
    with Session(other) as session:
        import_sources(session, payload)
        rows = ScrapeStore(session).list_sources()
        assert len(rows) == 1
        assert not rows[0].enabled
        assert Draft.model_validate_json(rows[0].payload).state == "unverified"


def test_export_omits_unverified_source_candidates():
    from resume_tailor_harness.discovery.scraper.tables import ScrapeSourceRow
    from resume_tailor_harness.services.scrape_transfer import export_sources

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        draft = Draft(
            source_id="candidate",
            url="https://example.com/jobs",
            state="unverified",
        )
        session.add(
            ScrapeSourceRow(
                id=draft.source_id,
                url=draft.url,
                revision=0,
                enabled=False,
                payload=draft.model_dump_json(),
            )
        )
        session.commit()

        assert export_sources(session) == '{"sources":[]}'


def test_source_reset_clears_cache_but_keeps_job_evidence_and_overrides():
    from resume_tailor_harness.discovery.scraper.contracts import (
        JobFacts,
        Observation,
        OverridePatch,
    )
    from resume_tailor_harness.discovery.scraper.tables import (
        ScrapeCacheRow,
        ScrapeObservationRow,
        ScrapeOverrideRow,
    )
    from resume_tailor_harness.services.scrape_transfer import reset_sources

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        store = ScrapeStore(session)
        draft = Draft(
            source_id="one",
            url="https://example.com/jobs",
            state="validated",
            validation=ValidationResult(valid=True),
            plan=BoardPlan(
                card_selector="article", link_selector="a", detail_selector=".jd"
            ),
        )
        store.save_draft(draft)
        store.approve(draft.id, 0)
        observation = Observation(
            source_id="one",
            revision=1,
            job_key="job-one",
            facts=JobFacts(source_url="https://example.com/jobs/1"),
        )
        store.save_observation(observation)
        store.set_override(
            "job-one",
            OverridePatch(field="title", value="Reviewed", expected_revision=0),
        )
        store.cache_observation("cached", observation)
        session.commit()

        reset_sources(session)
        session.commit()

        assert session.exec(select(ScrapeCacheRow)).all() == []
        assert len(session.exec(select(ScrapeObservationRow)).all()) == 1
        assert len(session.exec(select(ScrapeOverrideRow)).all()) == 1
