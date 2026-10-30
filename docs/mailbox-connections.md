# Email provider connections

Open **Settings → Email & notifications**. Gmail retains its existing Connect,
Sync, and draft controls. **More email providers** adds:

| Provider | Connection | Email retrieval |
| --- | --- | --- |
| Gmail / Google Workspace | Existing Google OAuth consent | Existing Gmail sync |
| Outlook / Microsoft 365 | Microsoft sign-in and read consent | Microsoft Graph inbox delta |
| Yahoo Mail | Server preset + app password | IMAP |
| iCloud Mail | Server preset + app-specific password | IMAP |
| Fastmail | Server preset + app password | IMAP |
| Custom provider | IMAP hostname, port, TLS mode, username, password | IMAP |

Microsoft and Google connections start with one click; provider sign-in and
permission consent are still required. Password-based providers use presets
instead of claiming to support OAuth that has not been configured.

## Custom mailbox setup

1. Choose **Add email account**, then a provider. Presets fill the hostnames and
   ports; custom servers are editable.
2. Enter the email address, IMAP username, and password. Prefer the provider's
   app-specific password. The username defaults to the email address but can be
   changed, including for iCloud accounts that require a different login.
3. Choose the folder to analyze (default `INBOX`). Folder names use their
   IMAP ASCII form, including modified UTF-7 where applicable.
4. Optionally enable SMTP and enter its separate credentials. SMTP is tested
   and saved, but cannot retrieve mail and is not used to send messages.
5. Select **Test & connect**. The connection is saved only after IMAP and any
   enabled SMTP credentials are verified.
6. Select **Sync & analyze**. Review proposed application updates in Notifications.

Both implicit TLS and mandatory STARTTLS verify certificates. Unencrypted
connections and private/loopback/link-local destinations are rejected. Public
DNS results are validated through the existing outbound security policy, then
pinned to the socket while preserving the original TLS hostname.

Up to 10 additional accounts are supported alongside Gmail. Connecting the same
IMAP host, port, username, and folder updates that connection's credentials.
Disconnect stops future sync and removes the saved credentials; cached evidence,
notifications, and prior review decisions remain until a jobs/all workspace reset.
To change an existing custom server address, disconnect it and add the new server.

Provider requirements and presets follow the official documentation:
[Yahoo](https://help.yahoo.com/kb/SLN4075.html),
[iCloud](https://support.apple.com/en-us/102525), and
[Fastmail](https://www.fastmail.help/hc/en-us/articles/1500000278342-Server-names-and-ports).
Provider plans and organization policies may restrict external mail access.

## Microsoft administrator setup

Create a Microsoft identity platform app registration that supports organizational
directories **and personal Microsoft accounts**, with a **Web** redirect URI:

```text
https://your-app.example/api/mailboxes/microsoft/callback
```

Set `MICROSOFT_OAUTH_CLIENT_ID` and `MICROSOFT_OAUTH_CLIENT_SECRET` on the server,
and configure `APP_BASE_URL` to the public origin. For local development, register
the matching localhost callback. Restart the API after changing environment values.
Without these settings the Microsoft button explains that administrator setup is
required. No user needs to enter an OAuth client secret in the browser.

The confidential authorization-code flow uses S256 PKCE, a short-lived opaque
HttpOnly browser cookie, and durable consume-once server state. Hosted callbacks
resolve the signed owner even if the session cookie is absent. Local workspaces
also work without `SESSION_SECRET`. Tokens request `offline_access User.Read
Mail.Read`, never Mail.Send or Mail.ReadWrite. Refreshes rotate saved tokens.
Revoked access is shown as requiring reconnection; temporary failures preserve
the connection. See Microsoft's
[delegated authorization documentation](https://learn.microsoft.com/en-us/graph/auth-v2-user).

## Analysis and scheduling

Manual sync starts a `mailboxSync` background run. Scheduled passes include all
connected accounts, using `GMAIL_SYNC_INTERVAL_HOURS` (default 6; 0 disables the
scheduler). A failed account does not stop other accounts. The existing
`GMAIL_SYNC_MAX_PAGES`, `GMAIL_MAX_MESSAGES`, and `GMAIL_MAX_AI_CALLS` settings
bound each account's work. IMAP caps pages at 100 messages; Microsoft requests
pages of 50. Rules run first; AI is optional and uses the existing evidence and
confidence checks.

IMAP scans only the configured folder with EXAMINE/read-only and BODY.PEEK. It
starts with recent mail, continues older UID ranges across runs, and checks new
UIDs before historical work. UIDVALIDITY changes restart discovery with distinct
message identities. Each message fetch is limited to its first 128 KiB; MIME
parsing ignores attachments and retains at most 4,000 body characters. Content
beyond that excerpt is not analyzed. Microsoft scans only Inbox through delta
pages, retaining the provider continuation and stable message IDs. Moved/deleted
messages do not undo reviewed decisions.

Page checkpoints and analysis receipts commit together. Failed reads leave
progress retryable; unchanged receipts reuse classification, and changes to the
application catalog rematch cached evidence. Latest-decision selection compares
receipt timestamps across Gmail and other connected accounts. Nothing automatically
changes application status: users still Accept or Dismiss notifications.

Credentials and OAuth tokens live in tenant-owned `mailbox_connections.json`,
with atomic writes and a connection lock shared by refresh, connect, disconnect,
and sync. Like existing Gmail tokens and `secrets.env`, this file contains
unencrypted secrets at rest: protect the workspace and its **full backups**.
It is excluded from settings bundles, never returned by listing endpoints, and
validation errors omit credential input. Disconnecting removes local access;
provider-side grants can also be revoked in the provider's account settings.

Connection errors use the standard API envelope with stable codes: `409` for a
busy connection store or account limit, `422` for invalid settings or rejected
credentials, `502` for malformed provider responses, and `503` for temporary
service failures. Field errors include only their location and type, never the
submitted value. The form focuses its error summary and links to affected fields.
Passwords remain in the editable form for retry, but never enter the shared
frontend mutation cache; closing the form clears its draft.

Normalized messages load cached receipts once per page. Repeated IDs in a delta
page use their last version, and changed content is reconsidered without losing
previous Accept/Dismiss decisions. Unchanged Microsoft tokens are not rewritten
on every sync. An additive index also supports decision lookups across accounts
on existing workspaces. An offline regression verifies one receipt query for a cached
100-message page; this is a database query count, not a live-provider speed claim.

Automated tests use simulated IMAP/SMTP and Microsoft responses. They validate
connection setup, OAuth state, token handling, read-only access, continuation,
analysis, tenant boundaries, and bilingual UI behavior. They do not establish
live provider consent or production delivery acceptance.
