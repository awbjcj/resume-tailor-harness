import pytest
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
        assert job_id is not None
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
        assert job is not None
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


def test_explicit_override_projects_latest_source_facts_for_a_progressed_job():
    from resume_tailor_harness.services.scrape_corrections import set_job_override
    from resume_tailor_harness.tracking.tables import Job, JobStatus

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
                jd_text="Build reliable software",
                remote_policy="onsite",
            ),
        )
        job_id = ingest_observation(session, first, store)
        assert job_id is not None
        job = session.get(Job, job_id)
        assert job is not None
        job.status = JobStatus.tailored.value
        session.add(job)
        session.commit()

        latest = first.model_copy(deep=True, update={"id": "latest"})
        latest.facts.remote_policy = "hybrid"
        latest.facts.jd_text = "New source description that has not been approved"
        ingest_observation(session, latest, store)
        set_job_override(
            session,
            job_id,
            "remote_policy",
            OverridePatch(field="remote_policy", value="remote", expected_revision=0),
        )

        criteria = project_source_facts(session, job_id, JobCriteria())
        session.refresh(job)
        assert criteria.remote_policy == "remote"
        assert job.status == JobStatus.tailored.value
        assert job.jd_text == "Build reliable software"


def test_override_on_first_observation_of_progressed_canonical_job_is_narrow():
    from resume_tailor_harness.services.scrape_corrections import set_job_override
    from resume_tailor_harness.tracking.tables import Job

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        job = Job(
            source="manual",
            url="https://example.com/jobs/1",
            title="Engineer",
            jd_text="Original approved description",
            status="tailored",
        )
        session.add(job)
        session.commit()
        assert job.id is not None and job.url is not None
        observation = Observation(
            source_id="board",
            revision=1,
            job_key="one",
            accepted=True,
            facts=JobFacts(
                source_url=job.url,
                title="Engineer",
                jd_text="Unapproved replacement",
                remote_policy="hybrid",
                employment_type="contract",
            ),
        )
        assert ingest_observation(session, observation, ScrapeStore(session)) == job.id
        set_job_override(
            session,
            job.id,
            "remote_policy",
            OverridePatch(field="remote_policy", value="remote", expected_revision=0),
        )
        original = JobCriteria(location="Boston")
        corrected = project_source_facts(session, job.id, original)
        assert corrected.remote_policy == "remote"
        assert corrected.location == "Boston" and corrected.employment_type is None
        assert (
            job.jd_text == "Original approved description" and job.status == "tailored"
        )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("FULL_TIME", "full_time"),
        ("Full-time", "full_time"),
        ("PartTime", "part_time"),
        ("Internship", "internship"),
        ("Temporary", None),
    ],
)
def test_source_employment_type_is_normalized(raw, expected):
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        observation = Observation(
            source_id="board",
            revision=1,
            job_key="one",
            accepted=True,
            facts=JobFacts(
                source_url="https://example.com/1",
                title="Engineer",
                jd_text="Build systems",
                employment_type=raw,
            ),
        )
        job_id = ingest_observation(session, observation, ScrapeStore(session))
        assert job_id is not None
        assert (
            project_source_facts(session, job_id, JobCriteria()).employment_type
            == expected
        )


def test_clearing_override_removes_obsolete_conflict_from_observation_view():
    from resume_tailor_harness.services.scrape_corrections import (
        set_job_override,
        clear_job_override,
    )
    from resume_tailor_harness.services.scrape_queries import job_observations

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
                source_url="https://example.com/1",
                title="Engineer",
                jd_text="Build systems",
                remote_policy="onsite",
            ),
        )
        job_id = ingest_observation(session, first, store)
        assert job_id is not None
        revision = set_job_override(
            session,
            job_id,
            "remote_policy",
            OverridePatch(field="remote_policy", value="remote", expected_revision=0),
        )
        newer = first.model_copy(deep=True, update={"id": "newer"})
        newer.facts.remote_policy = "hybrid"
        store.save_observation(newer)
        assert any(
            issue.kind == "conflict"
            for issue in job_observations(session, job_id)[-1].issues
        )
        clear_job_override(session, job_id, "remote_policy", revision)
        view = job_observations(session, job_id)[-1]
        assert view.effective_facts.remote_policy == "hybrid"
        assert not any(issue.kind == "conflict" for issue in view.issues)
