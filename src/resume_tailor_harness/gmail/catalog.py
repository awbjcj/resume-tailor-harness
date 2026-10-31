"""One compact, current matching snapshot per processing page."""

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json

from sqlalchemy import select
from sqlmodel import Session, col

from resume_tailor_harness.gmail.match import ApplicationMatcher
from resume_tailor_harness.tracking.tables import Application, Job


@dataclass(frozen=True)
class MatchingJob:
    id: int
    company: str | None
    title: str | None
    url: str | None
    source_identity: str | None


@dataclass(frozen=True)
class MatchingApplication:
    id: int
    job_id: int
    status: str
    submitted_at: datetime | None


class ApplicationCatalog:
    """Hide row expiration and reuse indexes when matching inputs are unchanged.

    Status is refreshed with every page but is not part of the matching revision:
    it controls proposals, not classification or message-to-application identity.
    The caller owns the transaction and commits between pages as before.
    """

    def __init__(self, processing_version: str, ai_enabled: bool):
        self.mode = (processing_version, ai_enabled)
        self.revision = ""
        self.apps: dict[int, MatchingApplication] = {}
        self.by_job: dict[int, MatchingApplication] = {}
        self.matcher: ApplicationMatcher[MatchingJob] = ApplicationMatcher([])

    def refresh(self, session: Session) -> None:
        rows = session.execute(
            select(
                col(Application.id),
                col(Application.job_id),
                col(Application.status),
                col(Application.submitted_at),
                col(Job.company),
                col(Job.title),
                col(Job.url),
                col(Job.source_identity),
            )
            .join(Job, col(Application.job_id) == col(Job.id))
            .where(col(Job.archived_at).is_(None))
            .order_by(col(Application.id))
        ).all()
        apps = {}
        jobs = []
        catalog = []
        for app_id, job_id, status, submitted, company, title, url, source_id in rows:
            assert app_id is not None
            apps[app_id] = MatchingApplication(app_id, job_id, status, submitted)
            jobs.append(MatchingJob(job_id, company, title, url, source_id))
            catalog.append((app_id, submitted, job_id, company, title, url, source_id))
        revision = sha256(
            json.dumps(
                [self.mode[0], catalog, self.mode[1]],
                default=str,
                sort_keys=True,
            ).encode()
        ).hexdigest()
        self.apps = apps
        self.by_job = {app.job_id: app for app in apps.values()}
        if revision != self.revision:
            self.matcher = ApplicationMatcher(jobs)
            self.revision = revision
