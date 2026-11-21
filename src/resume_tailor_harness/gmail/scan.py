"""Resumable mailbox discovery. Persist pages before their messages are processed."""

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone

from sqlmodel import Session

from resume_tailor_harness.gmail.client import BACKFILL_QUERY, mailbox_profile
from resume_tailor_harness.gmail.errors import GmailApiError
from resume_tailor_harness.gmail.requests import execute_read
from resume_tailor_harness.gmail.tables import GmailSyncState

HISTORY_TYPES = {
    "history": ("messageAdded",),
    "label_history": ("labelAdded", "labelRemoved"),
}
LANES = ("history", "recruiting", "inbox", "label_history")
WORK_LANES = (*LANES, "cached")


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
        self.account, self.latest = mailbox_profile(service)
        row = session.get(GmailSyncState, self.account)
        if row is None:
            # Capture the history boundary BEFORE the full scan: arrivals during
            # a multi-run backfill are caught independently through history.
            row = GmailSyncState(
                account=self.account,
                cursors={
                    "history": {"cursor": self.latest},
                    "label_history": {"cursor": self.latest},
                    **_backfills(),
                },
            )
        self.row: GmailSyncState = row
        self.cursors = deepcopy(row.cursors)
        if "label_history" not in self.cursors:
            # Old tokens are for the combined filter. Replay both filters from
            # the saved checkpoint and retain IDs already staged by that scan.
            history = self.cursors["history"]
            self.cursors["label_history"] = {
                "cursor": history["cursor"],
                "pending": history.pop("pending", []),
            }
            history.pop("page", None)
        self.history_checked: set[str] = set()
        self.restarted_backfills = False
        self.save()

    def save(self) -> None:
        self.row.cursors = deepcopy(self.cursors)
        self.session.add(self.row)
        self.session.commit()

    def has_work(self, lane: str) -> bool:
        cursor = self.cursors[lane]
        if cursor.get("pending"):
            return True
        if lane in HISTORY_TYPES:
            return lane not in self.history_checked and (
                bool(cursor.get("page")) or cursor["cursor"] != self.latest
            )
        return not cursor["done"]

    def next_lane(self, *, cached: bool) -> str | None:
        # Resume the rotation across runs, including a one-page budget.
        start = WORK_LANES.index(self.cursors.get("next_lane", "history"))
        for lane in WORK_LANES[start:] + WORK_LANES[:start]:
            available = cached if lane == "cached" else self.has_work(lane)
            if available:
                return lane
        return None

    def take(self, lane: str, limit: int) -> list[str]:
        cursor = self.cursors[lane]
        if not cursor.get("pending") and self.has_work(lane):
            self._stage_page(lane, limit)
        return self.cursors[lane].get("pending", [])[:limit]

    def complete(self, lane: str, count: int) -> None:
        if lane != "cached":
            cursor = self.cursors[lane]
            cursor["pending"] = cursor.get("pending", [])[count:]
        self.cursors["next_lane"] = WORK_LANES[
            (WORK_LANES.index(lane) + 1) % len(WORK_LANES)
        ]
        # Caller commits this with message receipts and notifications.
        self.row.cursors = deepcopy(self.cursors)
        self.session.add(self.row)

    def _stage_page(self, lane: str, limit: int) -> None:
        cursor = self.cursors[lane]
        params = {"pageToken": cursor["page"]} if cursor.get("page") else {}
        try:
            if lane in HISTORY_TYPES:
                result = execute_read(
                    self.service.users()
                    .history()
                    .list(
                        userId="me",
                        startHistoryId=cursor["cursor"],
                        historyTypes=list(HISTORY_TYPES[lane]),
                        maxResults=500,
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
            self.cursors[lane] = {"cursor": self.latest}
            self.history_checked.add(lane)
            if not self.restarted_backfills:
                for name, backfill in _backfills().items():
                    backfill["pending"] = self.cursors[name].get("pending", [])
                    self.cursors[name] = backfill
                self.restarted_backfills = True
            self.warn(
                "Gmail history expired. Resuming a full scan using cached results."
            )
            self.save()
            return
        if lane in HISTORY_TYPES:
            ids = []
            kinds = (
                ("messagesAdded",)
                if lane == "history"
                else ("labelsAdded", "labelsRemoved")
            )
            for history in result.get("history", []):
                for kind in kinds:
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
                self.history_checked.add(lane)
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
