"""Resumable mailbox discovery. Persist pages before their messages are processed."""

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256

from sqlmodel import Session

from resume_tailor_harness.gmail.client import BACKFILL_QUERY
from resume_tailor_harness.gmail.errors import GmailApiError
from resume_tailor_harness.gmail.requests import execute_read
from resume_tailor_harness.gmail.tables import GmailSyncState

LANES = ("history", "recruiting", "inbox")


def _backfills() -> dict:
    before = int(datetime.now(timezone.utc).timestamp()) + 1
    return {
        "recruiting": {"query": f"{BACKFILL_QUERY} before:{before}", "done": False},
        "inbox": {
            "query": f"-in:sent -in:drafts -in:spam -in:trash before:{before}",
            "done": False,
        },
    }


class MailboxScanner:
    def __init__(self, service, session: Session, warn: Callable[[str], None]):
        self.service, self.session, self.warn = service, session, warn
        profile = execute_read(service.users().getProfile(userId="me")) or {}
        if not profile.get("emailAddress") or not profile.get("historyId"):
            raise GmailApiError(
                "Gmail did not return a mailbox identity and sync cursor."
            )
        self.account = sha256(
            profile["emailAddress"].strip().lower().encode()
        ).hexdigest()
        self.latest = str(profile["historyId"])
        row = session.get(GmailSyncState, self.account)
        if row is None:
            # Capture the history boundary BEFORE the full scan: arrivals during
            # a multi-run backfill are caught independently through history.
            row = GmailSyncState(
                account=self.account,
                cursors={
                    "history": {"cursor": self.latest},
                    **_backfills(),
                },
            )
        self.row: GmailSyncState = row
        self.cursors = deepcopy(row.cursors)
        self.history_checked = False
        self.save()

    def save(self) -> None:
        self.row.cursors = deepcopy(self.cursors)
        self.session.add(self.row)
        self.session.commit()

    def has_work(self, lane: str) -> bool:
        cursor = self.cursors[lane]
        if cursor.get("pending"):
            return True
        if lane == "history":
            return not self.history_checked and (
                bool(cursor.get("page")) or cursor["cursor"] != self.latest
            )
        return not cursor["done"]

    def take(self, lane: str, limit: int) -> list[str]:
        cursor = self.cursors[lane]
        if not cursor.get("pending") and self.has_work(lane):
            self._stage_page(lane, limit)
        return self.cursors[lane].get("pending", [])[:limit]

    def complete(self, lane: str, count: int) -> None:
        cursor = self.cursors[lane]
        cursor["pending"] = cursor.get("pending", [])[count:]
        # Caller commits this with message receipts and notifications.
        self.row.cursors = deepcopy(self.cursors)
        self.session.add(self.row)

    def _stage_page(self, lane: str, limit: int) -> None:
        cursor = self.cursors[lane]
        params = {"pageToken": cursor["page"]} if cursor.get("page") else {}
        try:
            if lane == "history":
                result = execute_read(
                    self.service.users()
                    .history()
                    .list(
                        userId="me",
                        startHistoryId=cursor["cursor"],
                        historyTypes=["messageAdded", "labelAdded", "labelRemoved"],
                        maxResults=min(limit, 500),
                        **params,
                    ),
                    allow_missing=True,
                )
            else:
                result = execute_read(
                    self.service.users()
                    .messages()
                    .list(
                        userId="me",
                        q=cursor["query"],
                        maxResults=min(limit, 500),
                        **({"labelIds": ["INBOX"]} if lane == "inbox" else {}),
                        **params,
                    )
                )
        except GmailApiError as exc:
            # Page tokens may expire between runs. Restart just this listing;
            # cached receipts make the repeat safe and avoid downloading again.
            if (
                params
                and getattr(getattr(exc.__cause__, "resp", None), "status", None) == 400
            ):
                cursor.pop("page", None)
                self.save()
                self.warn(
                    "A Gmail page cursor expired. Saved results are retained; the scan will resume."
                )
                return
            raise
        if result is None:
            self.cursors = {"history": {"cursor": self.latest}, **_backfills()}
            self.history_checked = True
            self.warn(
                "Gmail history expired. Resuming a full scan using cached results."
            )
            self.save()
            return
        if lane == "history":
            ids = []
            for history in result.get("history", []):
                for kind in ("messagesAdded", "labelsAdded", "labelsRemoved"):
                    for entry in history.get(kind, []):
                        labels = set(entry.get("labelIds", []))
                        if (
                            kind == "messagesAdded"
                            or (kind == "labelsAdded" and "INBOX" in labels)
                            or (kind == "labelsRemoved" and labels & {"SPAM", "TRASH"})
                        ):
                            ids.append(entry["message"]["id"])
            if not result.get("nextPageToken"):
                cursor["cursor"] = str(result.get("historyId") or self.latest)
                self.history_checked = True
        else:
            ids = [entry["id"] for entry in result.get("messages", [])]
            cursor["done"] = not bool(result.get("nextPageToken"))
        next_page = result.get("nextPageToken")
        if next_page and next_page == cursor.get("page"):
            raise GmailApiError(
                "Gmail repeated a page cursor. Saved progress is retained; try again later."
            )
        cursor["page"] = next_page
        cursor["pending"] = list(dict.fromkeys(ids))
        self.save()
