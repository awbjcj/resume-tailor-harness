from resume_tailor_harness.gmail.client import EmailMessage
from resume_tailor_harness.gmail.match import match_email_to_application
from resume_tailor_harness.tracking.tables import Job


def _job(id_, company):
    return Job(id=id_, source="manual", company=company, title="Eng")


def test_matches_company_in_sender_domain():
    email = EmailMessage(
        sender="ta@acme.com", sender_domain="acme.com", subject="Hi", snippet=""
    )
    job = match_email_to_application(email, [_job(1, "Acme Corp"), _job(2, "Beta")])
    assert job is not None
    assert job.id == 1


def test_matches_company_in_subject_text():
    email = EmailMessage(
        sender="noreply@greenhouse.io",
        sender_domain="greenhouse.io",
        subject="Your application to Beta",
        snippet="",
    )
    job = match_email_to_application(email, [_job(1, "Acme"), _job(2, "Beta")])
    assert job is not None
    assert job.id == 2


def test_no_match_returns_none():
    email = EmailMessage(
        sender="x@unknown.com",
        sender_domain="unknown.com",
        subject="Newsletter",
        snippet="",
    )
    assert match_email_to_application(email, [_job(1, "Acme")]) is None


def test_matching_catalog_tracks_manual_application_url_requisitions():
    from sqlmodel import Session

    from resume_tailor_harness.db import init_db, make_engine
    from resume_tailor_harness.gmail.catalog import ApplicationCatalog
    from resume_tailor_harness.tracking.tables import Application

    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        job = Job(
            source="manual", company="Acme", title="Engineer",
            url="https://posting.example/jobs/1",
            criteria_json={"manual_details": {"application_url": "https://apply.example/jobs/JR123456"}},
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id
        assert job_id is not None
        session.add(Application(job_id=job_id, status="submitted"))
        session.commit()
        catalog = ApplicationCatalog("test", False)
        catalog.refresh(session)
        original = catalog.revision
        first = EmailMessage("Acme HR", "acme.com", "JR123456 update", "")
        match = catalog.matcher.match(first)
        assert match is not None and match.id == job_id
        job.criteria_json = {"manual_details": {"application_url": "https://apply.example/jobs/JR654321"}}
        session.add(job)
        session.commit()
        catalog.refresh(session)
        assert catalog.revision != original
        assert catalog.matcher.match(first) is None
        second = EmailMessage("Acme HR", "acme.com", "JR654321 update", "")
        match = catalog.matcher.match(second)
        assert match is not None and match.id == job_id


def _nvidia_job(id_, requisition, title="Senior Applied AI Engineer"):
    return Job(
        id=id_,
        source="workday",
        company="NVIDIA",
        title=title,
        url=f"https://nvidia.wd5.myworkdayjobs.com/jobs/Engineer_{requisition}-1",
    )


def test_requisition_selects_correct_application_regardless_of_order():
    email = EmailMessage(
        "NVIDIA HR <nvidia@myworkday.com>",
        "myworkday.com",
        "Thank you from NVIDIA",
        "We have decided not to move forward for the JR2025254 Senior Applied AI Engineer role.",
    )
    other = _nvidia_job(1, "JR2018181")
    target = _nvidia_job(2, "JR2025254")
    assert match_email_to_application(email, [other, target]) == target
    assert match_email_to_application(email, [target, other]) == target
    assert match_email_to_application(email, [other]) is None


def test_same_company_without_role_evidence_is_ambiguous():
    email = EmailMessage(
        "NVIDIA HR <nvidia@myworkday.com>", "myworkday.com", "NVIDIA update", ""
    )
    assert (
        match_email_to_application(
            email, [_nvidia_job(1, "JR2018181"), _nvidia_job(2, "JR2025254")]
        )
        is None
    )


def test_body_role_and_sender_name_disambiguate_company():
    email = EmailMessage(
        "NVIDIA HR <nvidia@myworkday.com>",
        "myworkday.com",
        "Update",
        "",
        body="Your application for Senior Applied AI Engineer was not selected.",
    )
    target = _nvidia_job(2, "JR2025254")
    assert (
        match_email_to_application(
            email, [_nvidia_job(1, "JR2018181", "Applied AI Engineer"), target]
        )
        == target
    )
