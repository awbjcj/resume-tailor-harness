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
from resume_tailor_harness.gmail.catalog import ApplicationCatalog
from resume_tailor_harness.gmail.propose import _CLASS_TO_STATUS, _is_forward
from resume_tailor_harness.gmail.tables import GmailReceipt, GmailSyncState
from resume_tailor_harness.tracking.tables import Notification, utcnow

PROCESSING_VERSION = "gmail-decisions-v4"


class MessageProcessor:
    def __init__(
        self,
        service,
        session: Session,
        account: str,
        classifier: SyncClassifier,
        checkpoint,
        *,
        source: str = "gmail",
    ):
        self.service, self.session, self.account, self.classifier = (
            service,
            session,
            account,
            classifier,
        )
        self.checkpoint = checkpoint
        self.source = source
        gmail_accounts = session.exec(
            select(GmailSyncState.account)
            .where(~col(GmailSyncState.account).startswith("mailbox-"))
            .limit(2)
        ).all()
        # Legacy notices use raw Gmail IDs. Additional IMAP/Graph accounts do
        # not make that identity ambiguous; a second Gmail identity does.
        self.legacy_account = gmail_accounts[0] if len(gmail_accounts) == 1 else None
        self.legacy_ids = source == "gmail" and self.legacy_account == account
        self.catalog = ApplicationCatalog(
            PROCESSING_VERSION, classifier.cache_ai_enabled
        )
        self.catalog.refresh(session)
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
        self.catalog.refresh(self.session)
        return list(
            self.session.exec(
                select(GmailReceipt.message_id)
                .where(
                    GmailReceipt.account == self.account,
                    GmailReceipt.revision != self.catalog.revision,
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
        self.catalog.refresh(self.session)
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
            or existing[mid].revision != self.catalog.revision
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
                or self.catalog.matcher.company_candidates(email)
                or self.catalog.matcher.match(email)
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
        receipt.revision = self.catalog.revision
        receipt.attempted_at = utcnow()
        receipt.email_json = asdict(email) if email else {}
        receipt.outcome = "ignored"
        if email is None or not email.incoming:
            return
        receipt.internal_date = email.internal_date
        job = self.catalog.matcher.match(email)
        if job is None:
            receipt.outcome = (
                "ambiguous"
                if self.catalog.matcher.company_candidates(email)
                else "unmatched"
            )
            self.stats[receipt.outcome] += 1
            return
        app = self.catalog.by_job[job.id]
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

    def process_emails(self, emails: list[EmailMessage]) -> None:
        """Analyze normalized mail from another transport using the same rules."""
        if not emails:
            return
        self.catalog.refresh(self.session)
        # Delta pages may repeat IDs; keep the last version and one receipt.
        unique = {email.message_id: email for email in emails if email.message_id}
        existing = {
            row.message_id: row
            for row in self.session.exec(
                select(GmailReceipt).where(
                    GmailReceipt.account == self.account,
                    col(GmailReceipt.message_id).in_(unique),
                )
            ).all()
        }
        affected: set[int] = set()
        for mid, email in unique.items():
            self.checkpoint()
            if not mid:
                continue
            receipt = existing.get(mid)
            if (
                receipt is not None
                and receipt.revision == self.catalog.revision
                and receipt.email_json == asdict(email)
            ):
                self.stats["cached"] += 1
                continue
            receipt = receipt or GmailReceipt(account=self.account, message_id=mid)
            if receipt.application_id is not None:
                affected.add(receipt.application_id)
            self._record(receipt, email)
            if receipt.application_id is not None:
                affected.add(receipt.application_id)
            self.session.add(receipt)
            self.stats["processed"] += 1
        self.session.flush()
        self._propose_latest(affected)

    def _classification_key(self, email: EmailMessage) -> str:
        # Exclude the application catalog: it affects association, not the email's
        # decision. Include actual classifier input, rules version and AI mode.
        return sha256(
            json.dumps(
                [
                    PROCESSING_VERSION,
                    self.classifier.cache_ai_enabled,
                    email.subject,
                    authored_text(email.body or email.snippet),
                ]
            ).encode()
        ).hexdigest()

    def restore_cleared_proposals(self) -> None:
        """Explicitly recover legacy bulk-cleared updates using cached evidence."""
        self.catalog.refresh(self.session)
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
        self._propose_latest(
            affected.intersection(self.catalog.apps), restore_cleared=True
        )

    def _refresh_cached_decisions(self, affected: set[int]) -> None:
        """Re-match stale evidence before comparing decisions across pages/accounts.

        Page refreshes can change the matching revision while earlier receipts
        still carry the old one. Reuse their classifications and bound identities;
        removing revision guards would instead trust obsolete associations.
        Read at most 500 receipts at a time and never fetch message bodies here.
        """
        visited: set[int] = set()
        while targets := affected - visited:
            visited.update(targets)
            after: tuple[str, str] | None = None
            while True:
                statement = select(GmailReceipt).where(
                    col(GmailReceipt.application_id).in_(targets),
                    GmailReceipt.revision != self.catalog.revision,
                    GmailReceipt.revision
                    != "",  # deferred classification stays retryable
                )
                if after is not None:
                    statement = statement.where(
                        or_(
                            col(GmailReceipt.account) > after[0],
                            (col(GmailReceipt.account) == after[0])
                            & (col(GmailReceipt.message_id) > after[1]),
                        )
                    )
                receipts = self.session.exec(
                    statement.order_by(
                        col(GmailReceipt.account),
                        col(GmailReceipt.message_id),
                    ).limit(500)
                ).all()
                if not receipts:
                    break
                after = (receipts[-1].account, receipts[-1].message_id)
                for receipt in receipts:
                    self.checkpoint()
                    attempted_at = receipt.attempted_at
                    self._record(
                        receipt,
                        EmailMessage(**receipt.email_json)
                        if receipt.email_json
                        else None,
                    )
                    if receipt.revision:
                        # Revalidating old evidence must not win the chronology
                        # tie-break against a just-arrived message with the same
                        # provider timestamp. Failed attempts still move back
                        # in the deferred-work queue.
                        receipt.attempted_at = attempted_at
                    if receipt.application_id is not None:
                        affected.add(receipt.application_id)
                    self.session.add(receipt)
                    self.stats["processed"] += 1
                self.session.flush()
                if len(receipts) < 500:
                    break

    def _propose_latest(
        self, affected: set[int], *, restore_cleared: bool = False
    ) -> None:
        if not affected:
            return
        if not restore_cleared:
            self._refresh_cached_decisions(affected)
        ranked = (
            select(
                GmailReceipt.account,
                GmailReceipt.message_id,
                func.row_number()
                .over(
                    partition_by=col(GmailReceipt.application_id),
                    order_by=(
                        col(GmailReceipt.internal_date).desc(),
                        col(GmailReceipt.attempted_at).desc(),
                        col(GmailReceipt.message_id).desc(),
                    ),
                )
                .label("position"),
            )
            .where(
                col(GmailReceipt.application_id).in_(affected),
                GmailReceipt.label != "none",
            )
            .subquery()
        )
        rows = self.session.exec(
            select(GmailReceipt)
            .join(
                ranked,
                (col(GmailReceipt.message_id) == ranked.c.message_id)
                & (col(GmailReceipt.account) == ranked.c.account),
            )
            .where(ranked.c.position == 1)
        ).all()
        latest: dict[int, GmailReceipt] = {}
        for row in rows:
            if row.application_id is not None:
                latest.setdefault(row.application_id, row)
        latest_ids = [self._receipt_notice_key(row) for row in latest.values()]
        latest_ids += [
            row.message_id
            for row in latest.values()
            if row.account == self.legacy_account
        ]
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
            if (mid := self._notice_identity(notice.message_id))
        ]
        known = (
            {
                (row.account, row.message_id): row
                for row in self.session.exec(
                    select(GmailReceipt).where(
                        col(GmailReceipt.account).in_(
                            {account for account, _ in pending_ids}
                        ),
                        col(GmailReceipt.message_id).in_(
                            [mid for _, mid in pending_ids]
                        ),
                    )
                ).all()
            }
            if pending_ids
            else {}
        )
        for notice in notices:
            current = latest.get(notice.application_id)
            identity = self._notice_identity(notice.message_id)
            cached = known.get(identity) if identity else None
            if (
                notice.state == "pending"
                and cached
                and cached.revision == self.catalog.revision
            ):
                corrected = _CLASS_TO_STATUS.get(cached.label)
                if (
                    cached.application_id != notice.application_id
                    or (
                        current
                        and current.revision == self.catalog.revision
                        and (current.account, current.message_id) != identity
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
        existing = {
            (n.application_id, self._notice_identity(n.message_id)): n for n in notices
        }
        for app_id, row in latest.items():
            # Explicit Gmail recovery may never resurrect another mailbox's
            # cleared evidence. Normal sync still compares chronology globally.
            if restore_cleared and row.account != self.account:
                continue
            app = self.catalog.apps.get(app_id)
            proposed = _CLASS_TO_STATUS.get(row.label)
            if (
                not app
                or row.revision != self.catalog.revision
                or not proposed
                or not _is_forward(app.status, proposed)
            ):
                continue
            notice = existing.get((app_id, (row.account, row.message_id)))
            if notice is not None:
                if notice.state == "superseded" or (
                    restore_cleared and notice.state == "cleared"
                ):
                    # Automatic supersession is reversible when classifier
                    # corrections make this decision current again. Claim the
                    # observed state so a concurrent dismissal stays final.
                    restored = self.session.execute(
                        update(Notification)
                        .where(
                            col(Notification.id) == notice.id,
                            col(Notification.state) == notice.state,
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
                    message_id=self._receipt_notice_key(row),
                )
            )

    @staticmethod
    def _evidence(row: GmailReceipt) -> str:
        email = EmailMessage(**row.email_json)
        return f"{email.subject}\n{authored_text(email.body or email.snippet)[:400]}".strip()

    def _notice_key(self, message_id: str) -> str:
        return f"{self.source}:{self.account}:{message_id}"

    @staticmethod
    def _receipt_notice_key(row: GmailReceipt) -> str:
        source = "mailbox" if row.account.startswith("mailbox-") else "gmail"
        return f"{source}:{row.account}:{row.message_id}"

    def _notice_identity(self, key: str) -> tuple[str, str] | None:
        if key.startswith(("gmail:", "mailbox:")):
            parts = key.split(":", 2)
            return (parts[1], parts[2]) if len(parts) == 3 else None
        return (self.legacy_account, key) if self.legacy_account else None

    def _raw_id(self, key: str) -> str | None:
        prefix = f"{self.source}:{self.account}:"
        if key.startswith(prefix):
            return key[len(prefix) :]
        return (
            key
            if self.legacy_ids and not key.startswith(("gmail:", "mailbox:"))
            else None
        )
