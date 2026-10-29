# Python client reference

```python
from resume_harness_sdk import ResumeHarness, APIError, RunFailed, RunTimeout

with ResumeHarness.from_env() as client:
    for job in client.iter_jobs(board="shortlist", minFit=70):
        detail = client.get_job(job["jobId"])
        print(detail["title"])
```

Install from a checkout with `python -m pip install ./sdk/python`; this package
is not yet published. Configure the URL and PAT in environment variables.
`ResumeHarness(base_url=..., api_key=..., timeout=30)` supports explicit values
retrieved from a secret manager and an optional HTTPX transport for offline tests.

| Method | Result / behavior |
| --- | --- |
| `me()` | Account/auth JSON |
| `list_sources()` | Configured sources response |
| `list_jobs(board="triage", page=1, page_size=50, **filters)` | `data` and `pagination` (`totalPages`) |
| `iter_jobs(board="shortlist", **filters)` | Iterates all board pages |
| `get_job(job_id)` | Full JD, criteria, versions, company intelligence |
| `approve_job(job_id)` | PATCH chosen raw/shortlisted job to approved; only for user-authorized preparation, never reset tailored/rendered stages |
| `add_job(jd_text=..., company=..., title=..., url=...)` | Immediately adds supplied text; returns job detail |
| `pull_jobs(source_ids=None, limit=None, refresh=False)` | Starts configured-source fetch; returns a run |
| `discover_jobs()` | Starts classification of raw jobs; returns a run |
| `tailor([job_id], deep=False)` | Starts hosted authoring and review; returns a run |
| `generate_cover_letters([job_id])` | Starts hosted cover-letter writing, fact checking, and PDF rendering; returns a run |
| `authoring_context(job_id)` | `profile`, `resumeSchema`, `jdText`, `contextRevision`, `styleGuide`, `lengthBudget` |
| `validate_resume(job_id, content, context_revision=...)` | `valid`, `critiques`; no LLM or save |
| `submit_resume(job_id, content, context_revision=..., agent="external")` | Starts paid server review; passing drafts become new versions |
| `get_run(run_id)` | Current run record |
| `list_runs(page=1, page_size=100)` | Active/recent runs in the server's visibility window |
| `wait(run_or_id, timeout=600, poll_interval=1)` | Terminal `done` record; raises on error/cancel/timeout |
| `cancel_run(run_id)` | Requests cancellation |
| `get_resume(version_id)` | Native structured resume JSON |
| `render_resume(version_id)` | Renders PDF and returns version metadata |
| `download_resume(version_id)` | PDF bytes; caller chooses file destination |
| `list_application_jobs(page=1, page_size=50)` / `iter_application_jobs(page_size=50)` | Approved/tailored/rendered, unarchived jobs without submission history |
| `application_context(job_id)` | Full job, readable prompt, personal `profile`, `profileRevision`, questions, attachments and `submissionPolicy` |
| `application_prompt(job_id)` | Full Markdown prompt including job description and personal information |
| `get_application_profile()` | `profile` and current `revision` |
| `update_application_profile(changes, revision=..., user_confirmed=True)` | Partial update of confirmed personal fields; camelCase keys. Name/address parts merge; lists replace in full (`[]` clears); empty strings clear text, nullable answers use null for unknown. |
| `list_application_questions(job_id=None, status=None, page=1, page_size=50)` | Paginated questions; job filter also includes reusable profile questions |
| `iter_application_questions(job_id=None, status=None, page_size=50)` | Iterates matching questions across pages |
| `record_application_question(question, job_id=None, scope="job", context="")` | Idempotently records an unanswered question; job scope requires job ID |
| `answer_application_question(id, answer, revision=..., user_confirmed=True)` | Saves confirmed answer; `None` clears it |
| `get_application_question(id)` | Question and its current revision for conflict reconciliation |
| `download_cover_letter(id)` | PDF bytes through the authenticated fixed API route |
| `select_resume(job_id, version_id)` | Stores a resume attachment choice; creates/updates a ready tracking application |
| `select_cover_letter(job_id, cover_letter_id)` | Stores a cover-letter attachment choice; does not upload or submit |
| `list_application_events(job_id)` | Timeline records; inspect before preparing a duplicate or retrying an event write |
| `record_application_event(job_id, event)` | Appends an event using camelCase JSON; `application_submitted` advances tracking, so use only after verified submission |

Filters use API names (`q`, `minFit`, `sortBy`, `status`, `source`), with CSV values
for multiselects. Use positive job/version IDs. A run's ID is `runId`; a job
detail's is `id`, and board rows use `jobId`. Run states are `pending`, `running`,
`cancelling`, `done`, `error`, `cancelled`. Inspect `result` even for `done`.
External submission results contain `passed`, `versionId` (null on rejection),
and `verdict.critiques`. API errors have status/code/details; failed runs expose
`RunFailed.run["errorCode"]`. Timeout does not cancel. Writes are not retried.

Save with `Path(...).open("xb")` when preserving an existing output matters.
Do not use server-returned filesystem paths as local paths or follow arbitrary
download URLs with the bearer token. `download_resume` uses a fixed API route.

Application response types live in `resume_harness_sdk.applications`. These
responses are validated at the HTTP boundary and keep additive fields. Invalid
responses raise `ResponseValidationError` without echoing personal data.
`PROFILE_STALE` / `QUESTION_STALE` are 409 conflicts: read and reconcile before
retrying. Questions are private workspace data and do not become resume evidence.
Only set `user_confirmed=True` after the user supplies or confirms the answer.
`APPLICATION_NOT_READY` means the context is no longer eligible; refresh the queue.

## Interactive application commands

Read [the apply skill](../../resume-harness-apply/SKILL.md) for the conversational
workflow and [its examples](../../resume-harness-apply/references/interactive-application.md)
for question/answer JSON, review and resumption, and submission tracking.

| CLI | Purpose |
| --- | --- |
| `approve JOB_ID` | Approve a specifically chosen raw/shortlisted job |
| `application-jobs --page N --page-size N` | Inspect the live eligible queue |
| `application-context JOB_ID` / `application-prompt JOB_ID` | Full JSON context / full Markdown prompt |
| `tailor JOB_ID` / `cover-letter JOB_ID` | Start missing document generation; wait on the returned run ID |
| `render VERSION_ID` / `download VERSION_ID --output FILE` | Render with current workspace settings / download local resume PDF |
| `download-cover-letter LETTER_ID --output FILE` | Download the generated letter PDF |
| `select-resume JOB_ID VERSION_ID` / `select-cover-letter JOB_ID LETTER_ID` | Remember exactly which eligible documents are being uploaded |
| `application-questions --job-id JOB_ID --status unanswered` | Matching job and reusable profile questions |
| `record-application-question --input FILE` | Record an exact live question and its context |
| `application-question QUESTION_ID` | Read its current answer/revision |
| `answer-application-question QUESTION_ID --input FILE` | Save a user-supplied answer with current revision and `userConfirmed: true` |
| `application-profile` / `update-application-profile --input FILE` | Read / PATCH only confirmed common fields |
| `application-events JOB_ID` | Read timeline and previous submission evidence |
| `record-application-event JOB_ID --input FILE` | Record a verified event; never use to represent a merely filled form |

Event creation is not idempotent. For a verified employer submission the body is
`{"kind": "application_submitted", "occurredAt": "ACTUAL_ISO_TIME_WITH_OFFSET",
"notes": "OBSERVED_CONFIRMATION"}`. Inspect timeline history after an ambiguous
failure before retrying. Submission history removes the job from the queue;
read `get_job` and events afterward instead of requesting application context.
The observed `occurredAt` can differ from the server's `submittedAt` transition
time. Neither this POST nor document selection performs an employer submission.
