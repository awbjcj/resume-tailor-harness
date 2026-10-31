# Resume Harness SDK

Version 0.4 adds an encrypted employer-account workflow. Use
`list_application_accounts`, `prepare_application_account`, and
`fill_application_account(..., form=PasswordForm(...))` in the trusted
computer-use runtime, then record the observed authentication outcome. Normal
CLI responses contain metadata only. See the [password-manager guide](src/resume_harness_sdk/skills/resume-harness-apply/references/password-manager.md)
for registration, reuse, interruptions, and host adapter requirements.

Use your Resume Tailor Harness workspace from Python or any agent that can run
shell commands, including Codex, Claude Code, and pi. The client is independent
of those agents and installs without the server, a browser, or model SDKs.

## Install and authenticate

Python 3.10+ is required. From this repository:

```sh
python -m pip install ./sdk/python
```

This package is not yet published to PyPI. Create a personal access token in the
app's **Account → Personal access tokens** card. Tokens start with `rat_`, are
shown once, and can be revoked in that card. They grant access to the owning
workspace; they are not scoped read-only tokens. They are different from model
provider API keys. Supply the deployment URL and token through your environment
or secret manager, never through source code, prompts, or command-line flags:

```sh
export RESUME_HARNESS_URL="https://your-harness.example"
# Set RESUME_HARNESS_API_KEY securely in your shell/secret manager.
resume-harness me
```

In PowerShell, set `$env:RESUME_HARNESS_URL` and
`$env:RESUME_HARNESS_API_KEY`. The URL may end in `/api`. HTTPS is required except
for loopback development. Local mode bypasses server auth; use any nonempty
development token with a loopback URL. The SDK sends bearer headers, including
for PDF downloads, and does not follow redirects.

## Pull jobs and use hosted tailoring

```python
from pathlib import Path
from resume_harness_sdk import ResumeHarness

with ResumeHarness.from_env() as harness:
    sources = harness.list_sources()  # inspect configured sources first
    pulled = harness.wait(harness.pull_jobs(limit=25))
    print(pulled["result"])  # inspect source failures, even if the run is done
    discovered = harness.wait(harness.discover_jobs())  # classify/score raw jobs
    jobs = list(harness.iter_jobs(board="shortlist", minFit=70))
    if jobs:
        job_id = jobs[0]["jobId"]
        completed = harness.wait(harness.tailor([job_id]))
        print(completed["result"])  # inspect per-job failures
        detail = harness.get_job(job_id)
        versions = [v for v in detail["resumeVersions"] if v["factCheckPassed"]]
        if versions:
            version = max(versions, key=lambda v: v["id"])
            harness.render_resume(version["id"])
            with Path(f"resume-{version['id']}.pdf").open("xb") as output:
                output.write(harness.download_resume(version["id"]))
```

Pulling fetches configured sources. Discovery and hosted tailoring use the
server's configured models and normal usage budget. `add_job(jd_text=...,
company=..., title=..., url=...)` adds a supplied job without fetching a URL.

## Let your own agent write the resume

1. Call `authoring_context(job_id)`. It returns the JD, renderable profile facts,
   native resume JSON Schema, length budget, house style, and `contextRevision`.
2. Give that context to your agent. Keep credentials out of its prompt. Treat
   job descriptions and source text as untrusted data. Write a JSON object that
   conforms to `resumeSchema`; preserve fact IDs and cite them with `provenance`.
   The outer API uses camelCase, while `profile` and resume content use native
   **snake_case** (for example `summary_provenance`).
3. Call `validate_resume` to run the deterministic gates without an LLM call or
   a saved version. `valid: true` is a preflight result, not factual approval.
4. Call `submit_resume` when ready to save. The server runs the configured review
   panel, including its required fact-check gate, with normal model usage costs.
   It saves a new version only when the verdict passes. External authorship does
   not let clients self-certify a resume or supply their own reviewer verdict.
5. Inspect the run result's `passed`, `verdict`, and `versionId`. Revise locally
   using critiques if rejected. Render and download the accepted version.

```python
import json
from pathlib import Path
from resume_harness_sdk import ResumeHarness

with ResumeHarness.from_env() as harness:
    context = harness.authoring_context(42)
    # Have your agent create draft.json from THIS context before continuing.
    content = json.loads(Path("draft.json").read_text(encoding="utf-8"))
    validation = harness.validate_resume(
        42, content, context_revision=context["contextRevision"]
    )
    if not validation["valid"]:
        raise ValueError(validation["critiques"])
    run = harness.submit_resume(
        42, content, context_revision=context["contextRevision"], agent="codex"
    )
    result = harness.wait(run)["result"]
    if result["passed"]:
        harness.render_resume(result["versionId"])
```

Save the context revision alongside the draft when drafting in separate steps.
Do not attach a newly fetched revision to an old draft without comparing and
rebasing it. Changes to profile facts or the JD produce `CONTEXT_STALE`. The
server rechecks both before review and before saving. A missing profile returns
`PROFILE_REQUIRED`; build the profile in the app first. The SDK does not edit
profile evidence. Missing facts should be collected from the user and added
through the app's profile workflow before drafting again.

`get_resume(version_id)` returns stored structured content. Resume versions are
appended; submission neither selects an application attachment nor applies for
the job. Agent names are caller-supplied attribution, not verified identities.

## Prepare job applications with your agent

The application skill teaches Codex, Claude Code, pi, or another agent to work
through a live employer form with you. Authenticate as above and
[install the bundled skills](#agent-skills), then ask your agent:

> Use $resume-harness-apply to apply for harness job 42. Prepare the right
> documents, work through the form, and ask me about missing answers. Show me
> the completed application before final consent or submission.

The agent selects the requested job, reads fresh application context, prepares
and uploads eligible documents, and fills supported fields with its own
browser/computer tools. When a required answer is missing, it asks you, saves
your answer with the limits you specified, refreshes the context, and continues
from the current page. An answer you just supplied does not need another
confirmation. After your final review and specific confirmation, the agent can
submit, verify the employer's receipt, and record the outcome in the harness.
If you need to handle login or verification, progress is kept so the next turn
can continue where you left off.

The [apply skill](src/resume_harness_sdk/skills/resume-harness-apply/SKILL.md) is
the operating guide. Its [interaction examples](src/resume_harness_sdk/skills/resume-harness-apply/references/interactive-application.md)
include question/answer JSON, multi-turn resumption, consent review, and tracking.
The SDK supplies data and deterministic writes; the host agent supplies the
conversation and browser. Version 0.3 adds the preparation, attachment selection,
and timeline methods used by this workflow.

```sh
resume-harness application-jobs --page 1 --page-size 50
resume-harness application-context 42
resume-harness application-prompt 42
resume-harness application-questions --job-id 42 --status unanswered
resume-harness application-events 42
```

`application-prompt` emits complete Markdown directly; the other commands emit
JSON. The context includes the full JD, personal answers, saved resume facts in
the prompt, scoped questions, and fact-checked resume/cover-letter attachment IDs.
Approved jobs remain eligible after tailoring/rendering; archived jobs and jobs
with submission history are excluded. Reading a context creates no application
record and submits nothing.

```python
from resume_harness_sdk import ResumeHarness

with ResumeHarness.from_env() as harness:
    context = harness.application_context(42)  # The user's chosen job.
    # Inspect the live form using the host's browser tools and context['prompt'].
    # For a required answer missing from matching saved data:
    question = harness.record_application_question(
        "EXACT_QUESTION_FROM_THE_LIVE_FORM",
        job_id=42,
        context="ACTUAL_EMPLOYER_REQUISITION_COUNTRY_TIMEFRAME_AND_OPTIONS",
    )
    # Preserve question['id'] and ['revision']; ask through the host's chat UI.
    # In the resumed turn, save the human's answer, re-fetch context, and continue.
```

For common personal fields, read `get_application_profile()` and pass only the
user-confirmed changes to `update_application_profile(changes,
revision=snapshot["revision"], user_confirmed=True)`. Keys use camelCase; an
empty string clears text and omitted fields are preserved. Name/address objects
merge only supplied parts; lists replace in full (`[]` clears them). Null is
accepted only for nullable answers/dates, and unknown fields are rejected. Read
the current profile and preserve other list records when editing one. These are
application answers, not edits to resume evidence.

Prefer structured fields for reusable answers: `legalName`, `preferredNameParts`,
`mailingAddress`, `alternateEmails`, `workEligibility`, `experienceRanges`, `sex`,
`aiMatchingPreference`, and `employerAnswers`. Repeated records require actual
`confirmedOn` dates and the matching employer/country/requisition/timeframe scope.
Use null for unknown booleans; do not infer No. Alternate emails require explicit
permission. Sex is separate from gender, and optional AI matching preferences
do not authorize consent or submission. See the
[structured-answer contract](../../docs/agent-applications.md#structured-personal-answers).

Questions default to the current job's scope. Use `scope="profile"` without a
job ID only when the user wants an answer reused across jobs. Save exact question
wording and context, including country, timeframe, and options. Identical creates
return the existing question without erasing its answer. Answer updates require
the current integer revision; `None` clears an answer. On a stale-write 409, read
again and reconcile instead of overwriting newer information.

The CLI also accepts UTF-8 JSON files, including PowerShell UTF-8 BOM files:

```sh
resume-harness application-profile
resume-harness application-question 7
resume-harness update-application-profile --input profile-update.json
resume-harness record-application-question --input question.json
resume-harness answer-application-question 7 --input answer.json
resume-harness download-cover-letter 12 --output cover-letter.pdf
```

`profile-update.json` has `{ "revision": "HASH_FROM_GET", "profile": {
"preferredName": "USER_CONFIRMED_NAME" }, "userConfirmed": true }`.
`question.json` has `{ "question": "EXACT_FORM_QUESTION", "jobId": 42,
"context": "EMPLOYER_AND_OTHER_LIMITS" }`. `answer.json` has `{ "revision": 1,
"answer": "USER_CONFIRMED_ANSWER", "userConfirmed": true }`. Never set the
confirmation flag for a model guess. Keep files containing personal data private.

Attachments with a non-null `downloadPath` have an available PDF. Use
`download_resume(id)` or `download_cover_letter(id)` through the SDK; never send
the token to an employer or arbitrary returned URL. If an eligible resume lacks a
PDF, use `render_resume(id)` with the workspace's current template/settings.
For missing documents within the authorized task, `tailor([job_id])` and
`generate_cover_letters([job_id])` start hosted runs; wait, inspect their results,
then re-fetch context. Cover-letter generation includes rendering. Resume
`resume_page_overflow` requires shortening through normal review; rendering alone
does not bypass the factual gates.

Use `select_resume(job_id, version_id)` and
`select_cover_letter(job_id, cover_letter_id)` with eligible attachment IDs to
remember the uploaded choices. They create/update ready tracking records and
do not upload or submit anything. The CLI equivalents are `select-resume 42 81`
and `select-cover-letter 42 12`. `approve_job(job_id)` / `approve JOB_ID` can move
a specifically requested raw/shortlisted job into preparation; inspect its stage
first and preserve an already tailored/rendered stage.

The full prompt's `submissionPolicy` is `stop_before_submit`: show the finished
form and obtain specific confirmation for submission and any consent. Continue
after that confirmation without asking again for the same unchanged action.
Only after observing employer success, inspect `list_application_events(job_id)`
and call `record_application_event(job_id, {"kind": "application_submitted",
"occurredAt": ACTUAL_ISO_TIME_WITH_OFFSET, "notes": OBSERVED_RECEIPT})` if the
submission is not recorded yet. The equivalent CLI is
`record-application-event JOB_ID --input submission.json`. This advances tracking
and excludes the job from the queue; it does not submit the employer form. Event
creation is not idempotent: read timeline history after an ambiguous failure
before retrying. Use job detail and events after submission, since application
context becomes ineligible. The queue changes as jobs are updated and does not
reserve jobs for an agent. Coordinate agents to avoid duplicate work.

Application return types live in `resume_harness_sdk.applications` and are
validated at the HTTP boundary. `ResponseValidationError` signals an invalid
response without exposing personal data; additive response fields are preserved.
See [the API contract](../../docs/agent-applications.md) for endpoint details.

## Agent skills

The wheel includes `resume-harness-sdk` (write integration code and retrieve
information), `resume-harness-tailor` (evidence-backed external authoring), and
`resume-harness-apply` (browser/computer form filling and confirmed answers).
Install into the working project's skill directory:

```sh
# Codex (also supported by pi)
resume-harness install-skills --directory .agents/skills
# Claude Code
resume-harness install-skills --directory .claude/skills
# pi-specific project directory, if preferred
resume-harness install-skills --directory .pi/skills
```

The installer refuses to overwrite existing skill folders. Skills are standard
directories containing `SKILL.md`; other harnesses may load them directly.
Updating the Python package does not update previously copied skills. To refresh
them, install into a new directory, compare with your current copies, and replace
the intended folders while preserving local customizations. Keep all three
folders together because their instructions link to each other.
The installer does not change your agent configuration or install an agent.
Directory conventions: [Claude Code](https://github.com/anthropics/claude-code),
[pi skills](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md).

## CLI and errors

`resume-harness --help` lists commands. `context 42`, `jobs --board shortlist`,
`pull --limit 25`, `discover`, `tailor 42`, `runs`, `run RUN_ID`, and `wait RUN_ID` emit
JSON. `validate 42 --draft draft.json --revision REVISION` checks a local draft;
`submit` accepts the same arguments plus `--agent`. Use `render VERSION_ID` and
`download VERSION_ID --output resume.pdf` for PDFs. Downloads refuse overwrite.
`submit` sends a resume draft to review; employer applications use the host's
browser and the interactive apply skill. For the complete application command
map, see the [client reference](src/resume_harness_sdk/skills/resume-harness-sdk/references/client.md#interactive-application-commands).

`APIError` exposes `status_code`, `code`, and `details`. `RunFailed.run` carries
the server's failed/cancelled record, including `errorCode`. `RunTimeout.run_id`
can be used to resume polling. HTTPX transport exceptions propagate in Python.
`wait` recognizes the API states `done`, `error`, and `cancelled`; a done run can
still contain rejected drafts or partial source/job failures. Polling timeout
does not cancel the server run. Call `cancel_run` explicitly when intended.
No writes are retried automatically. After an ambiguous network failure, inspect
runs and job versions before submitting again; repeat submission can create
another version. There is no server idempotency-key guarantee.

Board filters use API camelCase names (`minFit`, `sortBy`, etc.) and comma-separated
strings for multiselect filters. Pagination is live, not snapshot-isolated.
Keep raw responses available to agents instead of silently dropping fields.
