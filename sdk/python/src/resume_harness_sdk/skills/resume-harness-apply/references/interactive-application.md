# Interactive application examples

Use these patterns for a live application, with the real IDs, exact question
wording, options, and user answers. JSON files contain private applicant data;
keep them local to the task. The CLI reads UTF-8, including PowerShell UTF-8 BOM.

## Choose and prepare

```sh
resume-harness me
resume-harness application-jobs --page 1 --page-size 50
resume-harness application-context 42
resume-harness application-events 42
```

Use the requested job, not automatically the first row. If its raw/shortlisted
stage needs approval and the user requested preparation, inspect `job 42`, then
`approve 42`. Do not approve again after it is tailored/rendered.

If context contains eligible resume #81 without a PDF:

```sh
resume-harness render 81
resume-harness application-context 42
resume-harness download 81 --output resume-job-42-v81.pdf
resume-harness select-resume 42 81
```

Download commands refuse to overwrite an existing file; reuse a verified local
copy or choose another filename. Open the PDF with the host's available viewer,
then upload it with browser tools and inspect the employer's parsed fields.

If there is no eligible resume, `tailor 42` starts a run; save its `runId`, use
`wait RUN_ID`, inspect per-job results, and re-fetch context. For a required cover
letter, use `cover-letter 42`, wait and inspect `result.coverLetters`, then
re-fetch context. Use `download-cover-letter LETTER_ID --output letter.pdf` and
`select-cover-letter 42 LETTER_ID` for a passing, available attachment. There is
no separate SDK cover-letter render command.

## Ask, remember, and continue

Suppose the current live page asks how many days per week the applicant can
attend a particular office. Saved remote preference does not answer this.

```python
from resume_harness_sdk import ResumeHarness

with ResumeHarness.from_env() as harness:
    question = harness.record_application_question(
        "How many days per week can you work in our New York office?",
        job_id=42,
        context="Example Co; requisition ENG-42; US/New York; options: 0, 1, 2, 3, 4, 5",
    )
    # Preserve question['id'] and question['revision'] while waiting for the user.
```

Ask: “For Example Co's New York role, how many days per week can you attend the
office? The options are 0–5.” Keep the answer job-scoped by default.

If the user answers “Three, for this role,” save `"3 days per week"` to that job
question, select 3 on the live form, verify it, and continue. Do not convert it
into a general attendance preference. Do not ask them to confirm “Three” again.

```python
# In the resumed turn, use the ID saved above and read the current revision.
# question_id is the recorded question's ID retained in the working record.
with ResumeHarness.from_env() as harness:
    current = harness.get_application_question(question_id)
    # If another edit changed the answer, reconcile before overwriting it.
    harness.answer_application_question(
        current["id"], "3 days per week",
        revision=current["revision"], user_confirmed=True,
    )
    fresh_context = harness.application_context(42)
```

For a common field the user directly supplies, such as a preferred name:

```python
with ResumeHarness.from_env() as harness:
    snapshot = harness.get_application_profile()
    # Here user_supplied_name is the name the human just provided.
    harness.update_application_profile(
        {"preferredName": user_supplied_name},
        revision=snapshot["revision"], user_confirmed=True,
    )
    fresh_context = harness.application_context(42)
```

If a question already existed with an answer, match its scope before asking.
If two saved answers conflict, state the conflict and ask which applies. Blank
profile fields and unanswered questions carry no implied answer.

Equivalent CLI writes:

```sh
resume-harness record-application-question --input question.json
resume-harness application-question 7
resume-harness answer-application-question 7 --input answer.json
resume-harness update-application-profile --input profile-update.json
resume-harness application-context 42
```

`question.json`:

```json
{
  "question": "How many days per week can you work in our New York office?",
  "jobId": 42,
  "context": "Example Co; ENG-42; US/New York; options: 0, 1, 2, 3, 4, 5"
}
```

`answer.json`, only after the user answers and using the current revision:

```json
{"revision": 1, "answer": "3 days per week", "userConfirmed": true}
```

`profile-update.json`, only for the user's intended reusable personal change:

```json
{
  "revision": "HASH_FROM_CURRENT_PROFILE_GET",
  "profile": {"preferredName": "NAME_THE_USER_PROVIDED"},
  "userConfirmed": true
}
```

Profile writes preserve omitted fields; an empty string clears text. Nested
`legalName`, `preferredNameParts`, and `mailingAddress` objects merge supplied
parts. Lists such as `workEligibility` and `employerAnswers` replace in full:
read the current snapshot, preserve other records, and use `[]` only to clear a
list. Null is accepted only for nullable answers/dates; unknown fields fail.
Repeated records require actual `confirmedOn` dates and the precise scope of the
user's answer. Never parse legacy notes into structured guesses. Question answers
can be cleared with null. Question wording, context, and scope are immutable;
create a separate record if their meaning changes.

## Review and resume after confirmation

A useful review names the live employer/role/requisition and uploaded files,
summarizes material screening answers, and identifies the exact consent or
attestation still required. Ask for the specific final action, for example:

“The Example Co ENG-42 form is ready with resume v81. The saved authorization
answer and your three-day office answer are entered. The last checkbox certifies
the answers are accurate. Please review the completed form and confirm whether
to check that certification and submit this application.”

If the user says “Yes, certify and submit,” inspect the current page, perform
those unchanged actions, and verify success. Do not restart the application or
ask for the same confirmation again. If the form changed, resolve the change.

If the user handles login or a verification step, ask only for that handoff,
retain the current URL/page and outstanding questions, then inspect the page
again after they finish. Do not store passwords or verification codes in the
application profile, question records, or progress notes.

## Track verified submission

After observing the employer's receipt/status, read the timeline first:

```sh
resume-harness application-events 42
```

If the actual submission is not already recorded, write `submission.json` with
the observed ISO 8601 time including UTC offset and minimal useful evidence:

```json
{
  "kind": "application_submitted",
  "occurredAt": "2026-10-29T14:05:00-04:00",
  "notes": "Employer confirmation page observed; reference ENG-42-RECEIPT."
}
```

The time and receipt above are examples; never copy them as an observed event.

```sh
resume-harness record-application-event 42 --input submission.json
resume-harness job 42
```

The Python equivalents are `list_application_events(42)` and
`record_application_event(42, event)`. Creating this event advances tracking to
submitted; it does not submit the employer form. `occurredAt` is the observed
event time; `application.submittedAt` is the server's status-transition time and
may differ. Submitted history makes `application-context` ineligible; use `job`
and the timeline after submission.

An event write is not idempotent. After a transport/response-validation failure,
inspect the timeline before writing again. If an employer receipt exists but the
event is missing, repair tracking only. If the employer outcome is uncertain,
preserve that uncertainty and inspect the employer site before any retry.

A handoff or final report should distinguish:

- Prepared: form completed, review/consent/submission confirmation still pending.
- Blocked: exact question, login step, missing file, or unavailable browser tool.
- Uncertain: submission attempted, employer success not yet verified.
- Submitted: employer receipt/status verified, with tracking saved or its failure
  clearly reported.
