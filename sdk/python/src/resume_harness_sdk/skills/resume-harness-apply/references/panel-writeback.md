# Panel write-back and verification

The panel is **Settings > Application profile** (`/settings/application-profile`).
`get_application_profile()` and `update_application_profile()` access the same
saved settings. Question records also feed future application contexts; a
question-only save does not update a profile field.

| Confirmed information | Destination |
| --- | --- |
| Personal contact details or reusable preferences | Matching supported profile fields. |
| Country-specific eligibility or dated experience | Matching `workEligibility` or `experienceRanges` record, retaining country/specialty, actual `confirmedOn` date, and answer limits. |
| Employer/requisition/time-specific answers | Matching `employerAnswers` record with exact question and scope; use explicitly scoped `employerScreeningAnswers` or other matching notes only when structured storage does not fit. |
| Unfamiliar question and confirmed answer | Exact question/options/context in a job-scoped question record, plus a matching panel field or scoped entry when applicable. Profile question scope requires intended cross-job reuse. |
| Unknown answer | Unanswered question record; no invented profile value. |
| Consent, submission permission, navigation observations, or credentials | Do not store as reusable personal answers. Keep application-specific consent/progress in the private working record; credentials belong only in the password manager. |

Run this check as information arrives and before each handoff or outcome:

1. Compare all newly supplied facts, answers, and corrections against a fresh
   profile and all matching question pages, including optional answers. Honor
   requests not to retain information. Identical saved values need no duplicate
   write. Match employer, country, requisition, timeframe, units, and options.
2. Build the smallest supported patch from that snapshot. Nested name/address
   parts merge, but lists replace in full: retain unrelated records when changing
   one. Preserve other text-note entries and replace only the matching scoped
   answer instead of appending duplicates. Do not guess structured values, invent
   confirmation dates, truncate notes to fit limits, or send unsupported fields.
   If no suitable panel field exists, save the scoped question and mark the
   intended panel update `pending` with the limitation.
3. Save profile changes and question answers using their respective current
   revisions and `user_confirmed=True` only for actual user answers. Question
   wording/context/scope are immutable; changed meaning needs a separate record.
   Keep confirmation source/date in supported fields or the private working
   record, not invented API metadata. Track each independent write's result.
4. Read profile and affected questions back. Compare values, context/scope, and
   preservation of unrelated answers. While eligible, refresh application context
   and check applicable answers appear. After submission, context is ineligible;
   direct profile/question reads and ordinary job/events still work. Do not
   reopen or approve a submitted job to verify answers.
5. On `PROFILE_STALE` or `QUESTION_STALE`, reconcile competing values before a
   bounded retry. Ask only if a conflicting concurrent edit makes the intended
   correction unclear; honor an already explicit correction. After a timeout,
   read back before retrying and save only absent changes. Leave unresolved
   access, validation, or conflict failures `pending` and continue independent
   work. Never repeat employer actions to repair a panel save.

For a confirmed scalar change, the SDK sequence is:

```python
snapshot = harness.get_application_profile()
# user_supplied_name is the actual name the user confirmed.
harness.update_application_profile(
    {"preferredName": user_supplied_name},
    revision=snapshot["revision"], user_confirmed=True,
)
verified_profile = harness.get_application_profile()
```

For a question retained in the working record:

```python
current = harness.get_application_question(question_id)
# Reconcile any competing answer before writing the actual confirmed_answer.
harness.answer_application_question(
    current["id"], confirmed_answer,
    revision=current["revision"], user_confirmed=True,
)
verified_question = harness.get_application_question(current["id"])
```

Compare the readback values with the intended changes before marking success.
Record changed field names, question IDs/revisions/scopes, confirmation source/date,
and readback results in the private working record. Use `complete` only when all
intended saves are verified, `no_changes` when nothing new needs retaining, and
`pending` with the exact missing writes otherwise. A local journal, chat summary,
PATCH response, or save toast alone does not verify panel persistence. A blocked
draft can have complete write-back; a submitted application can have pending
panel saves. Load fresh saved answers next time and recheck expired or rolling
answers. Saved information never grants consent or bypasses resume fact checks.
