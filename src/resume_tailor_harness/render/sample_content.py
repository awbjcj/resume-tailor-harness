"""Deterministic resume content for template validation and previews."""

from resume_tailor_harness.models.profile import Contact, Education
from resume_tailor_harness.models.resume import (
    ResumeContent,
    TailoredBullet,
    TailoredExperience,
    TailoredProject,
    TailoredSkill,
)


def sample_resume_content() -> ResumeContent:
    return ResumeContent(
        contact=Contact(
            name="Alex Sample",
            headline="Software Engineer",
            email="alex@example.com",
            location="Remote",
        ),
        # Fictional preview content, never profile evidence.
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
