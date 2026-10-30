# Employer account password manager

Open Settings → Applications → Password manager to manage the employer logins
used by the interactive application SDK. You can save existing accounts, generate
passwords for registration, sign in again, update saved passwords after a reset,
and remove saved logins. Removing a login does not delete the employer account.

## Deployment and operation

Set `APPLICATION_VAULT_KEYS` in the server deployment's secret manager or private
environment file. Generate a dedicated key in an administrator-only terminal:

```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep that key out of source control, chats, workspace settings, and backups of
the encrypted data. The application does not generate or store a plaintext
encryption key beside the vault. Without a key, the password manager shows as
unavailable; application preparation continues normally. If the key is malformed
or the vault cannot be read, access is blocked and saved passwords are not replaced.

Enable “Create accounts during applications” to allow a trusted application
agent to generate accounts at the exact HTTPS origin of an approved job. Existing
saved logins remain usable with this preference off. Turning it off also stops
pending automatic registrations. Account creation does not consent to agreements
or final application submission. The host requests CAPTCHA, verification, SSO,
or user-only actions when encountered.

Credentials are encrypted with PyCA Fernet in the tenant's
`application-accounts.vault`. The deployment key is excluded from the tenant
settings overlay. The authenticated ciphertext includes the workspace owner ID,
so a vault copied into another user's workspace cannot be decrypted through
that user's API. Writes use a cross-process file lock, encrypted temporary file,
fsync, and atomic replacement. No plaintext database column or config stores
the passwords. Settings bundles exclude the vault; full workspace/data backups
include only the encrypted vault and must retain the external key separately.
Restore under the original user identity. Deletion removes the current record;
older encrypted backups may retain it.

The vault accepts up to 1,000 accounts within a 4 MiB encrypted-document limit.
Writes that would exceed the limit fail before replacing the previous vault,
so an oversized password or account cannot make existing logins unreadable.

For key rotation, set a comma-separated list with the new key first and the old
key second. Reads try both; every vault mutation rewrites the entire document
with the first key. Change/save the account-creation preference for each workspace
to rewrite its vault, verify it using the new key, then retire the old key.
Retain old keys separately if historical backups still need them. Losing all
matching keys makes those saved passwords unrecoverable. Server operators with
keys and data can decrypt the saved passwords. The vault provides encryption at
rest; it is not a zero-knowledge vault.

## Workflow and boundaries

1. `prepare` rechecks the approved, unarchived application queue and matches the
   tenant, normalized employer name, and exact HTTPS origin. Passwords are never
   matched by domain suffix, fuzzy company name, or job-description instruction.
2. New accounts require explicit registration opt-in and matching job/login
   origins. A cryptographically random password is saved before any browser
   action. Default: 24 characters with upper/lowercase, digits, and symbols.
3. Interrupted registration returns the same pending record and password. The
   host inspects the live page before retrying; only observed authentication
   marks the record active. Explicit rejection marks it as needing attention.
4. The SDK's `PasswordForm` adapter checks the actual target-frame origin and
   password field types before retrieving and before filling credentials. It
   returns metadata only and never clicks a button. Read the distributable
   [computer-use guide](../sdk/python/src/resume_harness_sdk/skills/resume-harness-apply/references/password-manager.md).
5. The next eligible role with the same employer and login origin uses the active
   credential. Filling stops if the revision is stale, the origin or employer
   changes, or a failure remains unresolved. The SDK does not reset passwords
   automatically or guess credentials.

The server does not control or observe the employer browser. A host with the
user's API token can explicitly retrieve a password through the scoped secret
endpoint and is trusted with that secret. The adapter must never log passwords
or route them through model-visible tool results. Hosts without a private fill
facility hand off sign-in to the user. The discovery scraper remains read-only.
Live employer acceptance is separate from local fixture tests.

Shared ATS hosts are scoped by employer as well as origin. One account per
employer/origin is supported. If the site redirects to another origin, or uses a
shared origin with ambiguous employer identity, require a verified user-managed
login instead of guessing. Mandatory agreements still need the user's decision.
Some employers' password policies or SSO flows may need manual handling.

## API

All routes use the existing tenant session/PAT guard. Browser mutations additionally
enforce same-origin requests. Success and error responses use `Cache-Control:
no-store`; validation errors never echo credential request inputs.

| Route | Purpose |
| --- | --- |
| `GET /api/application-accounts` | Safe metadata, availability, preference, revision |
| `PATCH /api/application-accounts/policy` | Confirmed, revision-checked registration preference |
| `POST /api/application-accounts` | User-confirmed existing login for an exact employer/site |
| `PATCH /api/application-accounts/{id}` | Confirmed current password after an employer-side reset |
| `DELETE /api/application-accounts/{id}?revision=N` | Remove current saved copy |
| `POST /api/jobs/{job_id}/application-account/prepare` | Reuse or generate a pending account; metadata only |
| `POST /api/jobs/{job_id}/application-accounts/{id}/secret` | Explicit secret transport to trusted host runtime |
| `POST /api/jobs/{job_id}/application-accounts/{id}/outcome` | Observed authentication, verification, or rejection |

Passwords never appear in application context, prompts, account lists, profile
answers, question records, event notes, or ordinary CLI output. These APIs are not
exposed as tools to internal model loops. All writes use deterministic operations
called by the user or host.
