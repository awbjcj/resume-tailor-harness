# Email notifications

Email subjects and bodies follow the language selected in the dashboard
(English or Simplified Chinese). The dashboard saves that selection to the
account when opened and when the language changes, so background digests and
account notices use it too. Existing accounts default to English until their
dashboard language is saved. Verification and password-reset emails use the
same account preference; registration codes use the language of the registration
page. Names, job titles and user-written reasons stay as entered. A delivery
already attempted keeps its rendered payload for retries and provider idempotency.
The notification settings, verification errors, and public unsubscribe pages
also use the selected interface language. There is no separate email-language
setting. Account notices waiting for their first delivery use the recipient's
latest saved choice; deletion notices retain that choice after account removal.

## Account activity notices

Hosted accounts automatically receive transactional notices at their **registered,
verified sign-in email address**, using the same platform Resend or SMTP provider
as registration and password reset. These notices do not use the optional digest
recipient and do not require digest opt-in. Disabling digests does not disable
account notices. Legacy accounts without a verified registered email cannot
receive them until they verify an account address.

Notices cover:

- Account creation and administrator deletion, disabling, and re-enabling.
- Administrator/member role changes, granting/revoking shared-key access, and
  changes to active-job and concurrent-run limits.
- Password changes and resets, Google identity linking/unlinking, personal access
  token creation/revocation, and revoking sign-in sessions.
- Registered-email changes: confirmation to the new verified address and a notice
  to the previous verified address.
- Credit grants, deductions, purchases, refunds, payment disputes, quota resets,
  individual allowance overrides, tier assignments, and tier configuration changes.
- Subscription activation, renewal, revocation, expiry, scheduled cancellation
  changes, and automatic quota-period renewals.

Notices describe the resulting settings, amounts, dates, and adjustment reason
where available. Passwords, verification codes, and access-token secrets are never
included in activity notices. Ordinary page reads and individual LLM usage charges
do not generate activity emails. Automatic period renewals and subscription expiry
are detected when the existing quota lifecycle advances the account; several
missed periods produce one renewal notice.

The operation and notice are committed together in the system database's
`account_emails` outbox. Failed transactions and unchanged settings do not send
notices; replayed billing webhooks and idempotent quota/subscription operations
do not create duplicate notices. Deletion notices retain the registered address
after account/workspace removal and remain held until cleanup succeeds. A cleanup
failure restores the account and removes its deletion notice.

The existing mail worker dispatches up to 50 account notices per minute while
the server runs, including notices for disabled/deleted accounts. Delivery failures
retry after 2, 4, 8 minutes, increasing to a maximum six-hour interval, and survive
restarts. The exact rendered HTML/text request and provider idempotency key are
persisted before sending. Workers lease requests without holding a database writer
lock during network delivery. SMTP has no idempotent send API, and Resend retains
idempotency keys for 24 hours: an ambiguous delivery failure can still duplicate
a notice, especially after a prolonged outage.

Both versions use Jinja templates `account_event.html` and `account_event.txt`,
with HTML autoescaping and the shared email layout. Configure the provider as
described below. `APP_BASE_URL` adds a link to the account page; account notices
can still deliver without it. No separate user setting or provider credential is
required. Restart the server after deploying to create the outbox table and start
the worker with the configured mail provider.

## Optional job-search digests

Open **Settings → Email notifications** to enter a recipient address, opt in,
choose **Daily**, **Weekly**, or **Every 30 days**, and select digest topics:

- **Jobs awaiting review:** the active shortlist count and up to ten recent jobs.
- **Job-search statistics:** active jobs, submitted applications, applications in
  interview, and offers. These are current totals, not changes since the last email.
- **Reminders:** up to ten upcoming interviews/assessments or offer deadlines
  before the next digest, plus up to ten stale applications due for follow-up.
  Archived jobs, closed/rejected applications, past events, and cancelled events
  are excluded from reminder content. Accepted, dismissed, and cleared follow-ups
  stay excluded until new application activity starts a new stale episode.
  Follow-up age uses `FOLLOW_UP_DAYS`.

Save the preferences, send a verification code, and enter the six-digit code.
Codes expire after 15 minutes and permit five attempts. Requests are limited to
one per minute and three per hour per workspace, with additional hosted
recipient/IP limits. Changing the recipient requires fresh verification and
invalidates previous verification and unsubscribe links. This does not change
the account's sign-in address.

Delivery starts one full selected interval after verification. Frequency changes
and opting back in restart that interval; previously verified unchanged addresses
do not need another code. The server checks due work once per minute while it is
running. Missed intervals produce one digest after restart, not a catch-up burst.
Empty digests are skipped unless statistics are enabled. Times are stored in UTC
and displayed in the browser's local time. Emails are currently in English; the
settings page supports English and Chinese.

**Turn off email notifications** stops future digests immediately. Each digest
also includes a public unsubscribe link and one-click unsubscribe headers. Opening
the link only displays a confirmation form, so an email scanner's GET cannot
unsubscribe someone. Submitting the form (or the mail client's one-click POST)
requires the opaque token and works without login. Registration, password reset,
and account security emails continue independently.

## Deployment

Notifications reuse `app.state.mailer`, the same provider used for registration
and password changes. There is no separate provider credential or user-configurable
SMTP server. Configure:

```dotenv
APP_BASE_URL=https://your-app.example.com
MAIL_FROM=Your App <notifications@your-verified-domain.example>

# Resend HTTPS API (takes precedence when both providers are configured)
RESEND_API_KEY=

# Or the existing SMTP provider
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_STARTTLS=true
```

`MAIL_FROM` falls back to `SMTP_FROM` and then `SMTP_USERNAME`. SMTP port 465
uses implicit TLS. `APP_BASE_URL` must be an absolute HTTP(S) origin and is used
for every digest link; request Host headers never set scheduled-email links.
Restart the application after changing deployment settings. Missing provider or
application URL configuration is shown in settings and prevents verification and
digest delivery, while still allowing preferences to be saved and disabled.

Jinja templates live in `src/resume_tailor_harness/mail/templates/`, with plain
text and autoescaped HTML versions. The provider receives both parts. Runtime
delivery uses Resend's HTTPS API directly or Python SMTP; the Resend CLI is not
a server runtime dependency.

Preferences, code hashes, consent tokens, schedule, and pending delivery requests
are stored in a new workspace database table created by the existing `init_db`
path. No destructive migration is required. They are tenant-isolated and excluded
from transferable settings bundles. Disabled accounts are skipped; local mode
only dispatches for the local workspace.

Delivery requests are persisted before sending. Dispatch and preference changes
use SQLite writer transactions to prevent overlapping sends and stale-recipient
races. Failed delivery retries after 1, 2, 4, then 6 hours, preserving the exact
payload and Resend idempotency key. Uncertain requests are retired after 12 hours,
before Resend's 24-hour idempotency retention expires, and scheduling resumes at
the normal interval. Opt-out or preference edits discard pending requests.
SMTP does not provide an idempotent send API: an ambiguous disconnect after
acceptance can still cause a duplicate despite a stable Message-ID.

Tests use fake mailboxes, an HTTP mock for Resend, and a fake SMTP transport;
they do not send live email or verify production delivery credentials.
