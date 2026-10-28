import re
from html import unescape
from urllib.parse import unquote

from resume_tailor_harness.gmail.client import EmailMessage
from resume_tailor_harness.tracking.tables import Job


def _company_token(company: str) -> str:
    """First alphanumeric word of a company name, lowercased."""
    words = re.findall(r"[a-z0-9]+", company.lower())
    return words[0] if words else ""


def _text(value: str) -> str:
    return " ".join(re.findall(r"[\w]+", unescape(value).casefold()))


def _message_text(email: EmailMessage) -> str:
    return f"{email.subject} {email.snippet} {email.body or ''}"


def matching_company_jobs(email: EmailMessage, jobs: list[Job]) -> list[Job]:
    """Company candidates only; a company match does not identify a role."""
    haystack = f"{email.sender} {_message_text(email)}".casefold()
    domain = (email.sender_domain or "").lower()
    candidates = []
    for job in jobs:
        if not job.company:
            continue
        token = _company_token(job.company)
        if not token:
            continue
        # Substring is fine inside a domain (e.g. "acme" in "mail.acmecorp.com"),
        # but a whole-word match in free text avoids "box" hitting "dropbox".
        if token in domain or re.search(rf"\b{re.escape(token)}\b", haystack):
            candidates.append(job)
    return candidates


def _requisitions(text: str) -> set[str]:
    # Workday's JR/R references and explicit REQ references, including URL suffixes.
    return {
        re.sub(r"[-_]", "", ref.lower())
        for ref in re.findall(
            r"(?<![a-z0-9])(?:jr|req|r)[-_]?\d{4,}(?![a-z0-9])", unquote(text), re.I
        )
    }


def match_email_to_application(email: EmailMessage, jobs: list[Job]) -> Job | None:
    """Select a unique requisition or role; never pick an arbitrary company row."""
    content = _message_text(email)
    references = _requisitions(content)
    if references:
        matches = [
            job
            for job in jobs
            if references
            & _requisitions(f"{job.url or ''} {job.source_identity or ''}")
        ]
        # An explicit reference to an untracked/different role must not fall back
        # to the only application at that company.
        return matches[0] if len(matches) == 1 else None
    candidates = matching_company_jobs(email, jobs)
    if len(candidates) == 1:
        return candidates[0]
    text = f" {_text(content)} "
    titled = [
        job for job in candidates if job.title and f" {_text(job.title)} " in text
    ]
    if not titled:
        return None
    # Prefer the complete title over a shorter title contained in it.
    longest = max(len(_text(job.title or "")) for job in titled)
    matches = [job for job in titled if len(_text(job.title or "")) == longest]
    return matches[0] if len(matches) == 1 else None
