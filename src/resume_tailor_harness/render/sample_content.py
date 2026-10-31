"""Deterministic resume content for template validation and previews."""

from resume_tailor_harness.models.profile import (
    AdditionalEntry,
    AdditionalSection,
    Contact,
    Education,
)
from resume_tailor_harness.models.resume import (
    ResumeContent,
    TailoredBullet,
    TailoredExperience,
    TailoredProject,
    TailoredSkill,
    TailoredAward,
    TailoredCertification,
    TailoredPublication,
)


def sample_resume_content(template_id: str | None = None) -> ResumeContent:
    content = ResumeContent(
        contact=Contact(
            name="Alex Sample",
            headline="Software Engineer",
            email="alex@example.com",
            location="Remote",
        ),
        # Fictional preview content, never profile evidence.
        summary="Software engineer building reliable services, practical data tools, and accessible interfaces with Python, PostgreSQL, and TypeScript.",
        summary_provenance=["sample-experience", "sample-project"],
        experience=[
            TailoredExperience(
                company="Acme Corp",
                title="Senior Engineer",
                start="2021",
                end="Present",
                provenance="sample-experience",
                bullets=[
                    TailoredBullet(
                        text="Cut p95 latency 40% by redesigning the query planner and introducing workload-aware indexes for customer reporting services.",
                        provenance="sample-latency",
                    ),
                    TailoredBullet(
                        text="Led a four-person team shipping a billing service, coordinating API contracts, rollout milestones, and operational ownership across engineering and finance.",
                        provenance="sample-leadership",
                    ),
                    TailoredBullet(
                        text="Built Python and PostgreSQL services with automated recovery, structured monitoring, and documented operational playbooks.",
                        provenance="sample-reliability",
                    ),
                    TailoredBullet(
                        text="Introduced staged deployments and service-level dashboards that helped on-call engineers identify regressions before they affected the wider customer base.",
                        provenance="sample-delivery",
                    ),
                ],
            ),
            TailoredExperience(
                company="Northstar Systems",
                title="Software Engineer",
                start="2018",
                end="2021",
                provenance="sample-earlier-role",
                bullets=[
                    TailoredBullet(
                        text="Delivered customer-facing APIs with contract tests and deployment checks, reducing integration defects by 25%.",
                        provenance="sample-apis",
                    ),
                    TailoredBullet(
                        text="Partnered with product and support teams to translate customer feedback into smaller, independently deployable improvements.",
                        provenance="sample-collaboration",
                    ),
                    TailoredBullet(
                        text="Migrated nightly reporting jobs to a monitored queue with retry policies, clear failure alerts, and a documented handover for support engineers.",
                        provenance="sample-reporting",
                    ),
                ],
            ),
        ],
        projects=[
            TailoredProject(
                name="Open Data Toolkit",
                tech=["Python", "SQL", "Docker"],
                provenance="sample-project",
                bullets=[
                    TailoredBullet(
                        text="Built an open-source validation pipeline that checks incoming datasets and reports actionable errors before downstream processing.",
                        provenance="sample-validation",
                    ),
                    TailoredBullet(
                        text="Designed a reproducible local development workflow with containerized services, automated tests, and contributor documentation.",
                        provenance="sample-workflow",
                    ),
                    TailoredBullet(
                        text="Published practical examples and schema migration guides so new contributors could add data sources without changing the shared validation engine.",
                        provenance="sample-project-docs",
                    ),
                ],
            ),
            TailoredProject(
                name="Service Health Dashboard",
                tech=["TypeScript", "SQL", "REST APIs"],
                provenance="sample-dashboard",
                bullets=[
                    TailoredBullet(
                        text="Created a service health dashboard that combines deployment history, error trends, and ownership information in a searchable operational view.",
                        provenance="sample-dashboard-view",
                    ),
                    TailoredBullet(
                        text="Added keyboard navigation, accessible status indicators, and focused component tests to make investigation workflows usable across desktop and mobile screens.",
                        provenance="sample-dashboard-accessibility",
                    ),
                ],
            ),
        ],
        skills={
            "Hard skills": [
                TailoredSkill(name="Python", provenance="sample-python"),
                TailoredSkill(name="PostgreSQL", provenance="sample-postgres"),
                TailoredSkill(name="SQL", provenance="sample-sql"),
                TailoredSkill(name="TypeScript", provenance="sample-ts"),
            ],
            "Engineering": [
                TailoredSkill(name="API design", provenance="sample-api-design"),
                TailoredSkill(name="Automated testing", provenance="sample-tests"),
                TailoredSkill(name="Observability", provenance="sample-observability"),
            ],
            "Tools": [
                TailoredSkill(name="Docker", provenance="sample-docker"),
                TailoredSkill(name="Git", provenance="sample-git"),
                TailoredSkill(name="Linux", provenance="sample-linux"),
            ],
        },
        education=[
            Education(
                institution="State University",
                degree="BSc",
                field="Computer Science",
            )
        ],
    )
    if template_id is not None:
        # Keep previews focused while demonstrating each layout's optional sections.
        content.experience = content.experience[:1]
        content.projects = content.projects[:1]
        content.certifications = [
            TailoredCertification(
                name="Cloud Architecture Certificate",
                issuer="Example Institute",
                date="2025",
                url="https://example.com/credential",
                provenance="sample-certification",
            )
        ]
        if template_id in {"modern", "technical", "minimal"}:
            content.portfolio = content.projects
            content.projects = []
            content.portfolio[0].url = "https://example.com/case-study"
        if template_id in {"graduate", "academic", "executive"}:
            content.awards = [
                TailoredAward(
                    name="Excellence Award",
                    issuer="Example Institute",
                    date="2025",
                    provenance="sample-award",
                )
            ]
        if template_id == "graduate":
            content.education[0].honors = ["Graduated with honors"]
            content.education[0].activities = ["Engineering Society"]
        if template_id == "academic":
            content.publications = [
                TailoredPublication(
                    title="Reliable Data Systems",
                    authors=["Alex Sample", "Sam Researcher"],
                    venue="Example Research Conference",
                    date="2025",
                    url="https://example.com/paper",
                    provenance="sample-publication",
                )
            ]
        if template_id in {"academic", "executive"}:
            content.additional_sections = [
                AdditionalSection(
                    title="Teaching"
                    if template_id == "academic"
                    else "Board & Advisory Roles",
                    entries=[
                        AdditionalEntry(
                            id="sample-additional-entry",
                            title="Systems Mentor",
                            organization="Example Institute",
                            description="Mentored engineering teams on reliable service design.",
                        )
                    ],
                )
            ]
    return content
