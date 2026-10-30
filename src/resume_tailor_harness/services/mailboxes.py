"""Connection management and resumable analysis, shared by API and scheduler."""

from contextlib import nullcontext
from pathlib import Path

from sqlalchemy import func
from sqlmodel import col, select

from resume_tailor_harness.config import Settings, get_settings
from resume_tailor_harness.db import get_session
from resume_tailor_harness.gmail.classify import (
    SyncClassifier,
    build_classifier_llm,
    classifier_available,
)
from resume_tailor_harness.gmail.client import EmailMessage
from resume_tailor_harness.gmail.processing import MessageProcessor
from resume_tailor_harness.gmail.tables import GmailReceipt, GmailSyncState
from resume_tailor_harness.mailboxes import imap, microsoft, store
from resume_tailor_harness.mailboxes.models import (
    MailboxConnectIn,
    MailboxError,
    MailboxOut,
    MailProviderOut,
)
from resume_tailor_harness.services.gmail_sync import _sync_lock
from resume_tailor_harness.tracking.tables import Notification


def run_connected_email_sync(engine, reporter, *, data_dir: Path) -> dict:
    from resume_tailor_harness.gmail.auth import token_path
    from resume_tailor_harness.gmail.errors import GmailApiError
    from resume_tailor_harness.services.gmail_sync import run_gmail_sync

    results, warnings = {}, []
    if token_path(data_dir).is_file():
        try:
            results["gmail"] = run_gmail_sync(engine, reporter, data_dir=data_dir)
        except GmailApiError as exc:
            warnings.append(str(exc))
    for account in store.read_accounts(data_dir).values():
        reporter.checkpoint()
        if account.get("needs_reconnect"):
            continue
        try:
            results[account["id"]] = run_mailbox_sync(
                engine, reporter, account_id=account["id"], data_dir=data_dir
            )
        except (MailboxError, GmailApiError) as exc:
            warnings.append(str(exc))
    return {"accounts": results, "warnings": warnings}


def providers(settings: Settings) -> list[MailProviderOut]:
    return [
        MailProviderOut(
            id="microsoft",
            name="Outlook / Microsoft 365",
            auth="oauth",
            available=microsoft.available(settings),
        ),
        MailProviderOut(
            id="yahoo",
            name="Yahoo Mail",
            auth="password",
            imap_host="imap.mail.yahoo.com",
            smtp_host="smtp.mail.yahoo.com",
            help_url="https://help.yahoo.com/kb/SLN4075.html",
        ),
        MailProviderOut(
            id="icloud",
            name="iCloud Mail",
            auth="password",
            imap_host="imap.mail.me.com",
            smtp_host="smtp.mail.me.com",
            smtp_port=587,
            smtp_security="starttls",
            help_url="https://support.apple.com/en-us/102525",
        ),
        MailProviderOut(
            id="fastmail",
            name="Fastmail",
            auth="password",
            imap_host="imap.fastmail.com",
            smtp_host="smtp.fastmail.com",
            help_url="https://www.fastmail.help/hc/en-us/articles/1500000278342-Server-names-and-ports",
        ),
        MailProviderOut(id="custom", name="Custom IMAP / SMTP", auth="password"),
    ]


def connect_custom(body: MailboxConnectIn, data_dir: Path) -> MailboxOut:
    identity = store.account_id(
        "imap", body.imap.host, str(body.imap.port), body.imap.username, body.folder
    )
    with store.connection_lock(data_dir):
        store.check_capacity(store.read_accounts(data_dir), identity)
        imap.verify_connection(body)
        account = body.model_dump(mode="json")
        # SecretStr deliberately masks normal serialization. Persist only here.
        account["imap"]["password"] = body.imap.password.get_secret_value()
        if body.smtp:
            account["smtp"]["password"] = body.smtp.password.get_secret_value()
        account["email"] = str(body.email)
        account["id"] = identity
        return store.save_account(account, data_dir)


def disconnect(account_id: str, data_dir: Path) -> None:
    with store.connection_lock(data_dir):
        accounts = store.read_accounts(data_dir)
        accounts.pop(account_id, None)
        store.write_accounts(accounts, data_dir)


def run_mailbox_sync(
    engine,
    reporter,
    *,
    account_id: str,
    data_dir: Path,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    reporter.begin(1, "Syncing mailbox")
    warnings: list[str] = []
    with _sync_lock(engine), store.connection_lock(data_dir):
        accounts = store.read_accounts(data_dir)
        account = accounts.get(account_id)
        if account is None:
            raise MailboxError(
                "This mailbox was disconnected. Connect it again in Settings."
            )
        try:
            if account["provider"] == "microsoft":
                if microsoft.refresh(account, settings):
                    store.write_accounts(accounts, data_dir)
            return _analyze(engine, reporter, account, settings, warnings)
        except microsoft.MicrosoftReconnect:
            account["needs_reconnect"] = True
            store.write_accounts(accounts, data_dir)
            raise


def _analyze(engine, reporter, account, settings, warnings) -> dict:
    try:
        ai_available = settings.gmail_max_ai_calls > 0 and classifier_available()
    except Exception:  # optional AI must not prevent deterministic analysis
        ai_available = False
        warnings.append(
            "AI classification is unavailable. Synced using email rules only."
        )
    classifier = SyncClassifier(
        None,
        build_classifier_llm if ai_available else None,
        settings.gmail_max_ai_calls,
        warnings.append,
        ai_available=ai_available,
    )
    account_key = "mailbox-" + account["id"]
    is_microsoft = account["provider"] == "microsoft"
    connection = (
        nullcontext(None)
        if is_microsoft
        else imap.open_mailbox(
            MailboxConnectIn.model_validate(account).imap, account["folder"]
        )
    )
    with connection as client, get_session(engine) as session:
        bounds = None if is_microsoft else imap.mailbox_bounds(client)
        row = session.get(GmailSyncState, account_key) or GmailSyncState(
            account=account_key
        )
        processor = MessageProcessor(
            None,
            session,
            account_key,
            classifier,
            reporter.checkpoint,
            source="mailbox",
        )
        # Reconsider cached evidence when jobs or AI availability change.
        stale = processor.stale_ids(min(settings.gmail_max_messages, 100))
        processor.process_emails(
            [
                EmailMessage(**receipt.email_json)
                for receipt in session.exec(
                    select(GmailReceipt).where(
                        GmailReceipt.account == account_key,
                        col(GmailReceipt.message_id).in_(stale),
                    )
                ).all()
                if receipt.email_json
            ]
        )
        session.commit()
        has_more = False
        reporter.begin(settings.gmail_sync_max_pages, "Analyzing mailbox emails")
        for page in range(settings.gmail_sync_max_pages):
            reporter.checkpoint()
            if is_microsoft:
                emails, cursor, has_more = microsoft.read_page(account, row.cursors)
            else:
                assert bounds is not None
                emails, cursor, has_more = imap.read_page(
                    client,
                    row.cursors,
                    min(settings.gmail_max_messages, 100),
                    reporter.checkpoint,
                    bounds=bounds,
                )
            processor.process_emails(emails)
            row.cursors = cursor
            session.add(row)
            # A failed fetch/classification never advances the durable cursor.
            session.commit()
            reporter.step(
                page + 1, label=f"Analyzed {processor.stats['processed']} emails"
            )
            if not has_more:
                break
        has_more = has_more or bool(processor.stale_ids(1))
        pending = session.exec(
            select(func.count())
            .select_from(Notification)
            .where(Notification.state == "pending")
        ).one()
        if has_more:
            warnings.append(
                "More emails remain. The next sync continues from saved progress."
            )
        return {
            "pending": pending,
            "has_more": has_more,
            "stats": {**processor.stats, "ai_calls": classifier.calls},
            "warnings": list(dict.fromkeys(warnings)),
        }
