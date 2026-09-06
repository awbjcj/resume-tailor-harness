from sqlmodel import Session

from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.discovery.scraper.contracts import (
    JobFacts,
    Observation,
    OverridePatch,
)
from resume_tailor_harness.discovery.scraper.store import ScrapeStore
from resume_tailor_harness.models.job import JobCriteria
from resume_tailor_harness.services.scrape_ingest import (
    ingest_observation,
    project_source_facts,
)


def test_explicit_unknown_override_survives_downstream_extraction():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        store = ScrapeStore(session)
        observation = Observation(
            source_id="board",
            revision=1,
            job_key="one",
            accepted=True,
            facts=JobFacts(
                source_url="https://example.com/jobs/1",
                title="Engineer",
                company="Example",
                jd_text="Build reliable software",
                remote_policy="remote",
            ),
        )
        job_id = ingest_observation(session, observation, store)
        store.set_override(
            "one", OverridePatch(field="remote_policy", value=None, expected_revision=0)
        )
        criteria = project_source_facts(
            session, job_id, JobCriteria(remote_policy="onsite")
        )
        assert criteria.remote_policy is None


def test_progressed_job_is_not_rewritten_by_new_source_observation():
    from resume_tailor_harness.tracking.tables import Job

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        store = ScrapeStore(session)
        first = Observation(
            source_id="board",
            revision=1,
            job_key="one",
            accepted=True,
            facts=JobFacts(
                source_url="https://example.com/jobs/1",
                title="Engineer",
                company="Example",
                jd_text="Original description",
            ),
        )
        job_id = ingest_observation(session, first, store)
        job = session.get(Job, job_id)
        job.status = "extracted"
        session.add(job)
        session.commit()
        changed = first.model_copy(deep=True, update={"id": "new"})
        changed.facts.jd_text = (
            "Much longer replacement description with substantially more requirements and duties. "
            * 20
        )
        ingest_observation(session, changed, store)
        session.refresh(job)
        assert job.jd_text == "Original description"
        assert job.status == "extracted"


def test_distinct_inline_postings_do_not_merge_on_board_url():
    from resume_tailor_harness.discovery.scraper.contracts import Observation, JobFacts
    from resume_tailor_harness.services.scrape_ingest import ingest_observation
    from resume_tailor_harness.discovery.scraper.store import ScrapeStore
    from resume_tailor_harness.db import make_engine, init_db
    from sqlmodel import Session, select
    from resume_tailor_harness.tracking.tables import Job

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        store = ScrapeStore(session)
        for key in ("one", "two"):
            item = Observation(
                source_id="board",
                revision=1,
                job_key=key,
                accepted=True,
                facts=JobFacts(
                    source_url="https://example.com/jobs",
                    posting_id=key,
                    title="Engineer",
                    company="Example",
                    jd_text="Build software for our team.",
                ),
            )
            ingest_observation(session, item, store, inline=True)
        assert len(session.exec(select(Job)).all()) == 2
