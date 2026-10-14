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
| `add_job(jd_text=..., company=..., title=..., url=...)` | Immediately adds supplied text; returns job detail |
| `pull_jobs(source_ids=None, limit=None, refresh=False)` | Starts configured-source fetch; returns a run |
| `discover_jobs()` | Starts classification of raw jobs; returns a run |
| `tailor([job_id], deep=False)` | Starts hosted authoring and review; returns a run |
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
