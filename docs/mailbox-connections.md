# Email provider connections

Open **Settings → Email & notifications**. Gmail has its own Connect, Sync, and
draft controls. Use **Other email accounts** to connect the additional providers
listed below:

| Provider | Connection | Email retrieval |
| --- | --- | --- |
| Gmail / Google Workspace | Existing Google OAuth consent | Existing Gmail sync |
| Outlook / Microsoft 365 | Microsoft sign-in and read consent | Microsoft Graph inbox delta |
| Yahoo Mail | Server preset + app password | IMAP |
| iCloud Mail | Server preset + app-specific password | IMAP |
| Fastmail | Server preset + app password | IMAP |
| Custom provider | IMAP hostname, port, TLS mode, username, password | IMAP |

For Microsoft and Google, select Connect, then sign in and grant access.
The other providers use server presets and passwords; OAuth is not configured
for them.

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

Connections use implicit TLS or mandatory STARTTLS, with certificate verification.
Unencrypted connections and private, loopback, or link-local destinations are
rejected. Public DNS results are checked against the outbound security policy.
The socket is then pinned to those addresses, using the original hostname for TLS.

Up to 10 additional accounts are supported alongside Gmail. Connecting the same
IMAP host, port, username, and folder updates that connection's credentials.
Disconnecting an account stops future syncs and removes its saved credentials.
Cached evidence, notifications, and prior review decisions remain until a
jobs/all workspace reset.
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
Without these settings, the Microsoft button asks users to contact their
administrator. Users do not enter an OAuth client secret in the browser.

The confidential authorization-code flow uses S256 PKCE and a short-lived opaque
HttpOnly browser cookie. Its server state is saved durably and can be consumed
only once. Hosted callbacks identify the signed owner even without the session
cookie. Local workspaces also work without `SESSION_SECRET`.
Tokens request `offline_access User.Read
Mail.Read`, never Mail.Send or Mail.ReadWrite. Refreshes rotate saved tokens.
Revoked access is shown as requiring reconnection; temporary failures preserve
the connection. See Microsoft's
[delegated authorization documentation](https://learn.microsoft.com/en-us/graph/auth-v2-user).

## Analysis and scheduling

Manual sync starts a `mailboxSync` background run. Scheduled syncs include all
connected accounts at the interval set by `GMAIL_SYNC_INTERVAL_HOURS` (default 6;
0 disables the scheduler). A failed account does not stop the others.
`GMAIL_SYNC_MAX_PAGES`, `GMAIL_MAX_MESSAGES`, and `GMAIL_MAX_AI_CALLS` limit the
work done for each account. IMAP caps pages at 100 messages; Microsoft requests
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

Page checkpoints and analysis receipts are committed together. Failed reads can
be retried from saved progress. Unchanged receipts reuse their classification;
when the application catalog changes, cached evidence is matched again.
The latest decision is selected by comparing receipt timestamps across Gmail and
other connected accounts. Email analysis does not change application status
automatically. Users review suggested updates with Accept or Dismiss.

Credentials and OAuth tokens are stored in each tenant's `mailbox_connections.json`.
Writes are atomic, and refresh, connect, disconnect, and sync share a connection
lock. Like Gmail tokens and `secrets.env`, this file stores unencrypted secrets:
protect the workspace and its **full backups**. Settings bundles exclude it,
listing endpoints never return it, and validation errors omit credential input.
Disconnecting removes local access. You can also revoke access in the provider's
account settings.

Connection errors use the standard API envelope with stable codes: `409` for a
busy connection store or account limit, `422` for invalid settings or rejected
credentials, `502` for malformed provider responses, and `503` for temporary
service failures. Field errors include only their location and type, never the
submitted value. The form focuses its error summary and links to affected fields.
Passwords remain in the editable form for retry, but never enter the shared
frontend mutation cache; closing the form clears its draft.

Cached receipts are loaded once per page of normalized messages. If an ID repeats
in a delta page, its last version is used. Changed content is analyzed again while
previous Accept/Dismiss decisions are kept. Sync does not rewrite unchanged
Microsoft tokens. An added index supports decision lookups across accounts in
existing workspaces. An offline regression test verifies that a cached 100-message
page needs one receipt query. It measures database queries, not live-provider speed.

Automated tests use simulated IMAP/SMTP and Microsoft responses. They validate
connection setup, OAuth state, token handling, read-only access, continuation,
analysis, tenant boundaries, and bilingual UI behavior. Live provider consent
and production delivery acceptance require separate validation.
