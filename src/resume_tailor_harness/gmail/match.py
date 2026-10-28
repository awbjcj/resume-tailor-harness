import re
from html import unescape
from urllib.parse import unquote, parse_qs, urlsplit

from resume_tailor_harness.gmail.client import EmailMessage, authored_text
from resume_tailor_harness.tracking.tables import Job


def _text(value: str) -> str:
    return " ".join(re.findall(r"[\w]+", unescape(value).casefold()))


def _message_text(email: EmailMessage) -> str:
    return f"{email.subject} {authored_text(email.body or email.snippet)}"


def matching_company_jobs(email: EmailMessage, jobs: list[Job]) -> list[Job]:
    return ApplicationMatcher(jobs).company_candidates(email)


def _requisitions(text: str) -> set[str]:
    # Workday's JR/R references and explicit REQ references, including URL suffixes.
    refs = {
        re.sub(r"[-_]", "", ref.lower())
        for ref in re.findall(
            r"(?<![a-z0-9])(?:jr|req|r)[-_]?\d{4,}(?![a-z0-9])", unquote(text), re.I
        )
    }
    refs.update(
        re.findall(
            r"\b(?:requisition|req|job)(?:\s*(?:id|number|#))?\s*[:#-]?\s*(\d{4,})\b",
            text,
            re.I,
        )
    )
    return refs


def _job_requisitions(job: Job) -> set[str]:
    refs = _requisitions(f"{job.url or ''} {job.source_identity or ''}")
    url = urlsplit(job.url or "")
    for key, values in parse_qs(url.query).items():
        if key.lower() in {"gh_jid", "jobid", "job_id", "requisitionid"}:
            refs.update(value for value in values if value.isdigit())
    refs.update(
        re.findall(
            r"(?:/|:)(\d{4,})(?:/|$)", f"{url.path} {job.source_identity or ''}".strip()
        )
    )
    return refs


def _company_names(company: str) -> set[tuple[str, ...]]:
    words = _text(company).split()
    if not words:
        return set()
    names = {tuple(words)}
    while words and words[-1] in {
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "llc",
        "ltd",
        "limited",
        "plc",
        "company",
        "co",
    }:
        words.pop()
    if words and words[0] == "the":
        words.pop(0)
    if words:
        names.add(tuple(words))
    return names


class ApplicationMatcher:
    """Build company/requisition indexes once per pass, not once per email."""

    def __init__(self, jobs: list[Job]):
        self.jobs = jobs
        self.refs: dict[str, set[int]] = {}
        self.names: dict[str, list[tuple[tuple[str, ...], int]]] = {}
        self.domains: dict[str, set[int]] = {}
        self.job_refs = [_job_requisitions(job) for job in jobs]
        for index, job in enumerate(jobs):
            for ref in self.job_refs[index]:
                self.refs.setdefault(ref, set()).add(index)
            for words in _company_names(job.company or ""):
                self.names.setdefault(words[0], []).append((words, index))
                self.domains.setdefault("".join(words), set()).add(index)

    def company_candidates(self, email: EmailMessage) -> list[Job]:
        return [self.jobs[i] for i in sorted(self._companies(email))]

    def _companies(self, email: EmailMessage) -> set[int]:
        found: set[int] = set()
        for label in email.sender_domain.lower().split("."):
            found.update(self.domains.get(label, ()))
        words = tuple(_text(f"{email.sender} {_message_text(email)}").split())
        for pos, word in enumerate(words):
            for name, index in self.names.get(word, ()):
                if words[pos : pos + len(name)] == name:
                    found.add(index)
        return found

    def match(self, email: EmailMessage) -> Job | None:
        candidates = self._companies(email)
        references = _requisitions(_message_text(email))
        if references:
            matches = set().union(*(self.refs.get(ref, set()) for ref in references))
            if candidates:
                matches &= candidates
            if matches:
                return self.jobs[next(iter(matches))] if len(matches) == 1 else None
            # For manually added jobs with no stored reference, require a title;
            # a conflicting stored reference always blocks a company fallback.
            candidates = {i for i in candidates if not self.job_refs[i]}
        elif len(candidates) == 1:
            return self.jobs[next(iter(candidates))]
        text = f" {_text(_message_text(email))} "
        titled = [
            (len(_text(self.jobs[i].title or "")), i)
            for i in candidates
            if self.jobs[i].title and f" {_text(self.jobs[i].title or '')} " in text
        ]
        if not titled:
            return None
        longest = max(size for size, _ in titled)
        matches = {i for size, i in titled if size == longest}
        return self.jobs[next(iter(matches))] if len(matches) == 1 else None


def match_email_to_application(email: EmailMessage, jobs: list[Job]) -> Job | None:
    return ApplicationMatcher(jobs).match(email)
