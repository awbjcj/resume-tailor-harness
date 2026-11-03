# Preparation and recovery

Use fresh server reads and the actual employer page to decide what remains.
An existing job status, a completed run, and a rendered PDF describe different
parts of the workflow. None independently proves an employer submission.

## Read the current work

`application_next_step(job_id)` / `application-next-step JOB_ID` reads the
server's `nextStep` from job detail:

| `kind` | Action within the user's request |
| --- | --- |
| `triage` | Inspect the saved JD and job; resolve the user's target. |
| `approve` | Approve the chosen role when preparation is authorized. |
| `tailor` | Prepare the required resume with hosted or external authoring. |
| `review` | Inspect failed gates or missing selected documents; repair or obtain a replacement choice. |
| `render` | Render the indicated eligible `resumeVersionId`, preserving explicit selections. |
| `apply` | Read fresh eligible application context and continue the live employer form. |
| `track` | Read job/timeline and employer status; avoid repeating a submission. |

`None` means no next step was provided, including by older servers. Inspect the
job, events and application context instead of assuming the job is ready.
`href` is a local app navigation destination; do not treat it as an API route.

`setup_status()` / `setup-status` reports readiness without changing settings.
Profile `freshness="refresh-needed"` and `pendingSourceCount` indicate evidence
not yet incorporated. Existing published evidence is not the same as newly
uploaded sources. If missing evidence prevents authoring, use the app's profile
workflow and obtain fresh authoring context after publication.

## Preserve exact materials

`application_context(job_id)` includes optional `materials` alongside eligible
legacy `attachments`. `get_application_prompt(job_id)` / `application-handoff
JOB_ID` reads the clipboard handoff envelope. `get_application_materials(job_id)`
/ `application-materials JOB_ID` projects that envelope's material metadata.
The latter two reads accept any existing job, so they cannot establish that
preparing or submitting it is still appropriate. Always check eligibility with
fresh context before working on the employer site.

The materials contract contains exact `selectedResumeVersionId`,
`selectedCoverLetterId`, and `items`:

- `isSelected` identifies the actual choice, even when a newer version exists.
- `applicationEligible` describes factual safety; `pdfAvailable` describes file
  availability. A PDF can exist for a blocked document. Upload requires both.
- `blockReason` can be `fact_lock_failed`, `fact_check_failed`, or
  `material_missing`. Do not silently fall back to a newer alternative.
- A non-null `downloadPath` is a relative authenticated app route. Download by
  ID through `download_resume` / `download_cover_letter`; keep the bearer token
  out of the employer browser and never follow an arbitrary returned URL.
- Missing or null `materials` means an older server supplied no metadata. Use
  job detail's `application` selected IDs together with legacy eligible attachments
  and selected flags. Hold a selected ID absent from eligible attachments for
  repair or a replacement choice; do not invent empty selected IDs.

For an eligible selected resume without its PDF:

```sh
resume-harness application-materials JOB_ID
resume-harness render EXACT_SELECTED_VERSION_ID
resume-harness application-context JOB_ID
resume-harness download EXACT_SELECTED_VERSION_ID --output LOCAL_FILE.pdf
```

When the user chooses to clear a blocked selection, use `deselect-resume JOB_ID`
or `deselect-cover-letter JOB_ID`, then re-read materials. These calls clear a
tracking pointer and retain the document. Selection changes do not submit.

`get_evidence_portfolio(version_id)` / `evidence-portfolio VERSION_ID` exposes
saved requirement coverage, selected facts, and evidence excerpts. Preserve
`gap` and `adjacent` classifications. A legacy portfolio 404 is not a reason to
regenerate an otherwise usable selected resume automatically.

## Import the user's actual role

Check existing jobs before `add_job_url(url)` / `add-job-url URL`. It starts a
server run; wait on its `runId` and inspect the result for a job ID, duplicate,
partial failure, or recovery requirement. `--no-browser` disables server browser
fallback. On recovery, inspect the real employer page using the host's tools.

For supplied or browser-captured JD text, use `create_job(body)` / `add-job
--input FILE` with camelCase JSON such as `{"jdText": "ACTUAL_JD", "url":
"ACTUAL_POSTING_URL", "company": "ACTUAL_EMPLOYER"}`. The existing
`add_job(jd_text=..., url=...)` Python method remains available. Do not submit an
invented description or repeat an ambiguous import before inspecting saved jobs.

## Recover completed work

Save active run IDs in the private working record. A `wait` timeout leaves work
running; poll the same ID. `list_runs` only covers the transient visibility
window. For an expired `get_run` record:

```sh
resume-harness run-completion SAVED_RUN_ID
resume-harness run-logs COMPLETION_ID_FROM_PREVIOUS_RESPONSE
resume-harness application-next-step JOB_ID
resume-harness application-materials JOB_ID
resume-harness application-events JOB_ID
```

`list_run_completions(limit=50, unread_only=False, surface="operations")` /
`run-completions --limit 50` returns a list, not a page. Its reads do not mark
entries read or replay writes. `get_run_logs` takes the integer completion ID;
older operations may return an empty log. `resultHref` and `resultAvailable`
resolve current app destinations; they are not the original run result or proof
that every job/document passed. Re-read current versions and their eligibility.

Only use `redo_jobs([job_id], stages=["render"])` / `redo JOB_ID --stage render`
when rerunning that stage is explicitly requested. Valid stages are `pull`,
`extract`, `tailor`, `render`; the server runs them in pipeline order and retains
prior artifacts and progress. Inspect `result.outcomes` for every failed/skipped
stage. History lookup is never permission to repeat a paid operation or an
employer submission. Keep employer outcome, harness tracking, and panel write-back
as separate entries in the private working record.
