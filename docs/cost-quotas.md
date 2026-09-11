# Cost quota operations

LLM quota enforcement uses integer USD micro-units (`$1 = 1_000_000`) to keep
accounting deterministic. Token counts remain available for platform-key and
bring-your-own-key analytics. They stop controlling access when
`COST_QUOTA_ENFORCEMENT=enforce`.

## Rollout

1. Start in `shadow` mode. Every `AgentRunner` and direct transcription call
   records provider/model-specific token lines and an effective-dated rate-card
   snapshot. The legacy weighted-token guard remains active.
2. Resolve each rate-coverage warning and compare computed costs with
   provider/Agno telemetry. Then set `COST_QUOTA_ENFORCEMENT=enforce`. Shared
   calls with an unknown rate fail closed. BYOK calls remain available and are
   marked unpriced.

## Defaults and resets

- `FREE` receives `$1` every seven days from assignment.
- `SUBSCRIBER` receives `$20` monthly from assignment. Month-end assignments
  clamp without drifting (January 31 → February 28 → March 31).
- Shared platform keys default to a `$500` UTC calendar-month cap.
- Administrators, free members, and subscribers all use shared platform keys
  first. Administrator usage counts toward the platform cap; member usage also
  consumes the member's recurring allowance and credits.
- After the applicable shared allowance is exhausted, the provider call uses
  the member's workspace key when configured. Without a workspace key, the
  existing quota-exhausted error is returned before any provider request.
- Credits survive resets and tier changes. The recurring allowance is spent first.
- Resetting a current period forgives its spend, refunds credits consumed during
  that period, and preserves its anchor.

Administrators use `/admin/quotas` for tier, account, bulk operation, rate-card,
and audit views. Bulk operations require a frozen preview, reason, and
idempotency key. All-member scope includes disabled non-admin accounts.
