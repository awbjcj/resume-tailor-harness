from sqlmodel import Session
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
