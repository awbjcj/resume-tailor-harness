"""Cached message processing and chronological, transaction-safe proposals."""

from dataclasses import asdict
from datetime import timezone
from hashlib import sha256
import json

from sqlalchemy import func, or_, update
from sqlmodel import Session, col, select

from resume_tailor_harness.gmail.classify import SyncClassifier
from resume_tailor_harness.gmail.client import (
    EmailMessage,
    authored_text,
    batch_read_messages,
    email_from_payload,
    extract_body,
)
from resume_tailor_harness.gmail.match import ApplicationMatcher
from resume_tailor_harness.gmail.propose import _CLASS_TO_STATUS, _is_forward
from resume_tailor_harness.gmail.tables import GmailReceipt, GmailSyncState
from resume_tailor_harness.tracking.queries import application_job_pairs
from resume_tailor_harness.tracking.tables import Notification, utcnow

PROCESSING_VERSION = "gmail-decisions-v3"


class MessageProcessor:
    def __init__(
        self,
        service,
        session: Session,
        account: str,
        classifier: SyncClassifier,
        checkpoint,
    ):
        self.service, self.session, self.account, self.classifier = (
            service,
            session,
            account,
            classifier,
        )
        self.checkpoint = checkpoint
        self.legacy_ids = (
            len(session.exec(select(GmailSyncState.account).limit(2)).all()) == 1
        )
        pairs = application_job_pairs(session)
        self.by_job = {job.id: app for app, job in pairs}
        self.apps = {app.id: app for app, _ in pairs}
        self.matcher = ApplicationMatcher([job for _, job in pairs])
        catalog = [
            (
                app.id,
                app.submitted_at,
                job.id,
                job.company,
                job.title,
                job.url,
                job.source_identity,
            )
            for app, job in pairs
        ]
        self.revision = sha256(
            json.dumps(
                [PROCESSING_VERSION, sorted(catalog), classifier.max_calls > 0],
                default=str,
                sort_keys=True,
            ).encode()
        ).hexdigest()
        self.stats = {
            "processed": 0,
            "cached": 0,
            "classification_cache_hits": 0,
            "metadata_reads": 0,
            "body_reads": 0,
            "matched": 0,
            "unmatched": 0,
            "ambiguous": 0,
            "restored": 0,
        }

    def stale_ids(self, limit: int) -> list[str]:
        return list(
            self.session.exec(
                select(GmailReceipt.message_id)
                .where(
                    GmailReceipt.account == self.account,
                    GmailReceipt.revision != self.revision,
                )
                .order_by(col(GmailReceipt.attempted_at))
                .limit(limit)
            ).all()
        )

    def process(
        self, ids: list[str], *, recruiting: bool, refresh: bool = False
    ) -> None:
        if not ids:
            return
        existing = {
            row.message_id: row
            for row in self.session.exec(
                select(GmailReceipt).where(
                    GmailReceipt.account == self.account,
                    col(GmailReceipt.message_id).in_(ids),
                )
            ).all()
        }
        # History can rediscover a message already read by a backfill. Its
        # content is unchanged; only previously excluded/missing messages need
        # new metadata to detect recovery from spam/trash or a missing read.
        refresh_ids = {
            mid
            for mid in ids
            if refresh
            and (
                mid not in existing
                or not existing[mid].email_json
                or not existing[mid].email_json.get("incoming", True)
            )
        }
        work = [
            mid
            for mid in ids
            if mid in refresh_ids
            or mid not in existing
            or existing[mid].revision != self.revision
            or (
                recruiting
                and existing[mid].email_json
                and not existing[mid].email_json.get("recruiting_candidate")
            )
        ]
        self.stats["cached"] += len(ids) - len(work)
        fresh = [mid for mid in work if mid in refresh_ids or mid not in existing]
        metadata = (
            batch_read_messages(self.service, fresh, checkpoint=self.checkpoint)
            if fresh
            else {}
        )
        self.stats["metadata_reads"] += len(fresh)
        emails: dict[str, EmailMessage] = {}
        for mid in work:
            if mid in existing and existing[mid].email_json and mid not in refresh_ids:
                email = EmailMessage(**existing[mid].email_json)
                email.recruiting_candidate |= recruiting
                emails[mid] = email
            elif metadata.get(mid) is not None:
                emails[mid] = email_from_payload(
                    mid, metadata[mid] or {}, recruiting=recruiting
                )
                if mid in existing and emails[mid].incoming:
                    emails[mid].body = existing[mid].email_json.get("body")
        body_ids = [
            mid
            for mid, email in emails.items()
            if email.incoming
            and email.body is None
            and (
                email.recruiting_candidate
                or self.matcher.company_candidates(email)
                or self.matcher.match(email)
            )
        ]
        bodies = (
            batch_read_messages(
                self.service, body_ids, full=True, checkpoint=self.checkpoint
            )
            if body_ids
            else {}
        )
        self.stats["body_reads"] += len(body_ids)
        for mid in body_ids:
            if bodies[mid] is None:
                emails.pop(mid)
            else:
                emails[mid].body = authored_text(
                    extract_body((bodies[mid] or {}).get("payload", {}))
                )
        affected: set[int] = set()
        for mid in work:
            self.checkpoint()
            receipt = existing.get(mid) or GmailReceipt(
                account=self.account, message_id=mid
            )
            if receipt.application_id is not None:
                affected.add(receipt.application_id)
            self._record(receipt, emails.get(mid))
            if receipt.application_id is not None:
                affected.add(receipt.application_id)
            self.session.add(receipt)
        self.session.flush()
        self._propose_latest(affected)
        self.stats["processed"] += len(work)

    def _record(self, receipt: GmailReceipt, email: EmailMessage | None) -> None:
        classification_key = self._classification_key(email) if email else ""
        reuse_classification = (
            bool(classification_key)
            and receipt.classification_version == classification_key
            and receipt.outcome == "matched"
            and bool(receipt.revision)
        )
        previous_label = receipt.label
        receipt.classification_version = ""
        receipt.application_id = None
        receipt.label = "none"
        receipt.revision = self.revision
        receipt.attempted_at = utcnow()
        receipt.email_json = asdict(email) if email else {}
        receipt.outcome = "ignored"
        if email is None or not email.incoming:
            return
        receipt.internal_date = email.internal_date
        job = self.matcher.match(email)
        if job is None:
            receipt.outcome = (
                "ambiguous" if self.matcher.company_candidates(email) else "unmatched"
            )
            self.stats[receipt.outcome] += 1
            return
        app = self.by_job[job.id]
        if (
            receipt.bound_application_id is not None
            and receipt.bound_application_id != app.id
        ):
            # Removing/archiving a role must not silently transfer its old mail
            # to the remaining role at that company.
            receipt.outcome = "ambiguous"
            self.stats["ambiguous"] += 1
            return
        if app.submitted_at and email.internal_date:
            submitted = app.submitted_at.replace(tzinfo=timezone.utc)
            # Do not attach a previous hiring cycle's mail to a new application.
            if email.internal_date < int(
                submitted.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
                * 1000
            ):
                return
        receipt.application_id = app.id
        receipt.bound_application_id = app.id
        receipt.outcome = "matched"
        self.stats["matched"] += 1
        # Completed "none" decisions are useful cache entries too. Rematching
        # after a catalog change must not spend tokens reviewing the same text.
        if reuse_classification:
            receipt.label = previous_label
            receipt.classification_version = classification_key
            self.stats["classification_cache_hits"] += 1
        else:
            receipt.label, retry = self.classifier.classify(email)
            if retry:
                receipt.revision = ""
                receipt.outcome = "retry"
            else:
                receipt.classification_version = classification_key

    def _classification_key(self, email: EmailMessage) -> str:
        # Exclude the application catalog: it affects association, not the email's
        # decision. Include actual classifier input, rules version and AI mode.
        return sha256(
            json.dumps(
                [
                    PROCESSING_VERSION,
                    self.classifier.max_calls > 0,
                    email.subject,
                    authored_text(email.body or email.snippet),
                ]
            ).encode()
        ).hexdigest()

    def restore_cleared_proposals(self) -> None:
        """Explicitly recover legacy bulk-cleared updates using cached evidence."""
        affected = set(
            self.session.exec(
                select(Notification.application_id)
                .where(
                    Notification.state == "cleared",
                    Notification.proposed_status != "",
                )
                .distinct()
            ).all()
        )
        self._propose_latest(affected.intersection(self.apps), restore_cleared=True)

    def _propose_latest(
        self, affected: set[int], *, restore_cleared: bool = False
    ) -> None:
        if not affected:
            return
        ranked = (
            select(
                GmailReceipt.message_id,
                func.row_number()
                .over(
                    partition_by=col(GmailReceipt.application_id),
                    order_by=(
                        col(GmailReceipt.internal_date).desc(),
                        col(GmailReceipt.message_id).desc(),
                    ),
                )
                .label("position"),
            )
            .where(
                GmailReceipt.account == self.account,
                col(GmailReceipt.application_id).in_(affected),
                GmailReceipt.label != "none",
            )
            .subquery()
        )
        rows = self.session.exec(
            select(GmailReceipt)
            .join(
                ranked,
                col(GmailReceipt.message_id) == ranked.c.message_id,
            )
            .where(GmailReceipt.account == self.account, ranked.c.position == 1)
        ).all()
        latest: dict[int, GmailReceipt] = {}
        for row in rows:
            if row.application_id is not None:
                latest.setdefault(row.application_id, row)
        latest_ids = [self._notice_key(row.message_id) for row in latest.values()]
        if self.legacy_ids:
            latest_ids += [row.message_id for row in latest.values()]
        notices = self.session.exec(
            select(Notification).where(
                col(Notification.application_id).in_(affected),
                Notification.proposed_status != "",
                or_(
                    col(Notification.state) == "pending",
                    col(Notification.message_id).in_(latest_ids),
                ),
            )
        ).all()
        pending_ids = [
            mid
            for notice in notices
            if notice.state == "pending"
            if (mid := self._raw_id(notice.message_id))
        ]
        known = (
            {
                row.message_id: row
                for row in self.session.exec(
                    select(GmailReceipt).where(
                        GmailReceipt.account == self.account,
                        col(GmailReceipt.message_id).in_(pending_ids),
                    )
                ).all()
            }
            if pending_ids
            else {}
        )
        for notice in notices:
            current = latest.get(notice.application_id)
            raw_id = self._raw_id(notice.message_id)
            cached = known.get(raw_id or "")
            if (
                notice.state == "pending"
                and cached
                and cached.revision == self.revision
            ):
                corrected = _CLASS_TO_STATUS.get(cached.label)
                if (
                    cached.application_id != notice.application_id
                    or (
                        current
                        and current.revision == self.revision
                        and current.message_id != raw_id
                    )
                    or not corrected
                ):
                    notice.state = "superseded"
                    self.session.add(notice)
                elif corrected != notice.proposed_status:
                    # A versioned classifier correction must update the review
                    # card as well as its cache. Accepted/dismissed cards stay put.
                    notice.kind = corrected
                    notice.proposed_status = corrected
                    notice.evidence = self._evidence(cached)
                    self.session.add(notice)
        existing = {(n.application_id, self._raw_id(n.message_id)): n for n in notices}
        for app_id, row in latest.items():
            app = self.apps.get(app_id)
            proposed = _CLASS_TO_STATUS.get(row.label)
            if (
                not app
                or row.revision != self.revision
                or not proposed
                or not _is_forward(app.status, proposed)
            ):
                continue
            notice = existing.get((app_id, row.message_id))
            if notice is not None:
                if restore_cleared and notice.state == "cleared":
                    # Claim only a still-cleared row: a concurrent explicit
                    # dismissal must never be undone by this recovery.
                    restored = self.session.execute(
                        update(Notification)
                        .where(
                            col(Notification.id) == notice.id,
                            col(Notification.state) == "cleared",
                        )
                        .values(
                            state="pending",
                            kind=proposed,
                            proposed_status=proposed,
                            evidence=self._evidence(row),
                        )
                        .returning(col(Notification.id))
                    ).first()
                    self.stats["restored"] += int(restored is not None)
                continue
            self.session.add(
                Notification(
                    application_id=app_id,
                    kind=proposed,
                    proposed_status=proposed,
                    evidence=self._evidence(row),
                    message_id=self._notice_key(row.message_id),
                )
            )

    @staticmethod
    def _evidence(row: GmailReceipt) -> str:
        email = EmailMessage(**row.email_json)
        return f"{email.subject}\n{authored_text(email.body or email.snippet)[:400]}".strip()

    def _notice_key(self, message_id: str) -> str:
        return f"gmail:{self.account}:{message_id}"

    def _raw_id(self, key: str) -> str | None:
        prefix = f"gmail:{self.account}:"
        if key.startswith(prefix):
            return key[len(prefix) :]
        return key if self.legacy_ids and not key.startswith("gmail:") else None
