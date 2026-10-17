from resume_tailor_harness.api.schemas.config import ApplicationProfileDoc
from resume_tailor_harness.models.profile import (
    Award,
    Bullet,
    Certification,
    Contact,
    Education,
    Experience,
    Language,
    Link,
    ProfileFacts,
    Project,
    Publication,
    Skill,
    Volunteer,
)
from resume_tailor_harness.profile.store import save_facts
from resume_tailor_harness.services.application_prompt import build_application_prompt
from resume_tailor_harness.tracking.tables import Job


def test_formats_saved_json_as_readable_qualifications_without_internal_metadata(
    tmp_path,
):
    path = tmp_path / "facts.json"
    save_facts(
        ProfileFacts(
            contact=Contact(name="Zoë Applicant"),
            summary="Build reliable services.",
            education=[
                Education(
                    institution="Example University",
                    degree="BS",
                    field="CS",
                    start="2016",
                    end="2020",
                    gpa="3.8",
                    honors=["Honors"],
                    relevant_coursework=["Algorithms"],
                    activities=["Robotics club"],
                )
            ],
            experience=[
                Experience(
                    company="Acme",
                    title="Engineer",
                    start="2020",
                    current=True,
                    location="Boston",
                    employment_type="Full-time",
                    tech=["Python"],
                    bullets=[
                        Bullet(
                            text="Built a reliable service",
                            source_ref="private/source.pdf",
                        )
                    ],
                )
            ],
            projects=[
                Project(
                    name="Useful project",
                    description="Open-source tool",
                    role="Maintainer",
                    start="2021",
                    end="2022",
                    tech=["Python"],
                    url="https://example.com/project",
                    repo_url="https://example.com/repo",
                    highlights=[Bullet(text="Implemented the parser")],
                    stars=9001,
                    forks=7001,
                    topics=["internal-topic"],
                ).model_copy(update={"extra": {"private_note": "secret note"}})
            ],
            skills={"Programming": [Skill(name="Python", context="Used at Acme")]},
            certifications=[
                Certification(
                    name="Cloud certification",
                    issuer="Cloud Org",
                    date="2023",
                    credential_id="CERT-1",
                )
            ],
            publications=[
                Publication(
                    title="A useful paper",
                    venue="Journal",
                    authors=["Zoë"],
                    date="2024",
                )
            ],
            awards=[
                Award(
                    name="Engineering award",
                    issuer="Acme",
                    description="For reliable services",
                )
            ],
            languages=[Language(language="English", proficiency="Fluent")],
            volunteer=[
                Volunteer(
                    organization="Community",
                    role="Mentor",
                    start="2022",
                    description="Taught programming",
                )
            ],
        ),
        path,
    )
    prompt = build_application_prompt(
        Job(source="manual", title="Engineer", company="New Co"),
        ApplicationProfileDoc(),
        path,
    )
    assert "- Full name: Zoë Applicant" in prompt
    assert "## Profile summary\n\nBuild reliable services." in prompt
    assert "### BS in CS — Example University\n- Dates: 2016 – 2020" in prompt
    for text in [
        "GPA: 3.8",
        "Honors: Honors",
        "Relevant coursework: Algorithms",
        "Activities: Robotics club",
    ]:
        assert text in prompt
    assert "### Engineer — Acme\n- Dates: 2020 – Present" in prompt
    assert "- Built a reliable service" in prompt
    assert "- Programming: Python (Used at Acme)" in prompt
    for text in [
        "Useful project",
        "Open-source tool",
        "Maintainer",
        "Implemented the parser",
        "https://example.com/repo",
    ]:
        assert text in prompt
    for text in [
        "Cloud certification",
        "Cloud Org",
        "CERT-1",
        "A useful paper",
        "Journal",
        "Engineering award",
        "Volunteer role: Mentor",
        "Language: English — Fluent",
    ]:
        assert text in prompt
    for text in [
        "private/source.pdf",
        "secret note",
        "internal-topic",
        "9001",
        "7001",
        "source_ref",
        "schema_version",
        '"current":',
        "null",
        "[]",
    ]:
        assert text not in prompt


def test_contact_overrides_replace_resume_links_and_preserve_other_links(tmp_path):
    path = tmp_path / "facts.json"
    save_facts(
        ProfileFacts(
            contact=Contact(
                name="Resume Name",
                email="resume@example.com",
                location="Boston",
                work_authorization="Resume authorization",
                links=[
                    Link(label="LinkedIn", url="https://linkedin.com/in/old"),
                    Link(label="Website", url="https://old.example.com"),
                    Link(label="GitHub", url="https://github.com/example"),
                    Link(label="Duplicate GitHub", url="https://github.com/example"),
                ],
            )
        ),
        path,
    )
    prompt = build_application_prompt(
        Job(source="manual", title="Engineer"),
        ApplicationProfileDoc(
            full_name="Application Name",
            email="new@example.com",
            address="123 Main St\nBoston, MA",
            linkedin_url="https://linkedin.com/in/new",
            portfolio_url="https://new.example.com",
            work_authorization="Authorized in Canada",
        ),
        path,
    )
    assert "- Full name: Application Name" in prompt
    assert "- Email: new@example.com" in prompt
    assert "- Address: 123 Main St\n  Boston, MA" in prompt
    assert "- Work authorization: Authorized in Canada" in prompt
    assert "Resume Name" not in prompt
    assert "resume@example.com" not in prompt
    assert "Resume authorization" not in prompt
    assert "https://linkedin.com/in/old" not in prompt
    assert "https://old.example.com" not in prompt
    assert prompt.count("https://github.com/example") == 1
    assert prompt.count("https://linkedin.com/in/new") == 1
    assert "- Location: Boston" not in prompt


def test_omits_blank_answers_but_preserves_explicit_no_and_multiline_notes(tmp_path):
    prompt = build_application_prompt(
        Job(source="manual", title="Engineer"),
        ApplicationProfileDoc(
            sponsorship_needed="No",
            veteran_status="No",
            disability_status="Prefer not to disclose",
            education_notes="Course completed in 2024.\nCertificate available on request.",
        ),
        tmp_path / "missing.json",
    )
    assert "- Sponsorship needed: No" in prompt
    assert "- Veteran status: No" in prompt
    assert "- Disability status: Prefer not to disclose" in prompt
    assert (
        "- Education: Course completed in 2024.\n  Certificate available on request."
        in prompt
    )
    assert "Expected salary:" not in prompt
    assert "Race / ethnicity:" not in prompt
    assert "## Skills" not in prompt
    assert "Not provided" not in prompt


def test_missing_end_date_does_not_claim_current_employment(tmp_path):
    path = tmp_path / "facts.json"
    save_facts(
        ProfileFacts(
            contact=Contact(name="Applicant"),
            experience=[
                Experience(
                    company="Old Co",
                    title="Engineer",
                    start="2020",
                    end=None,
                    current=False,
                ),
            ],
        ),
        path,
    )
    prompt = build_application_prompt(
        Job(source="manual", title="Engineer"), ApplicationProfileDoc(), path
    )
    assert "- Dates: From 2020" in prompt
    assert "Present" not in prompt
    assert "Current role" not in prompt
