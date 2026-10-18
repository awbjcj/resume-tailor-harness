# Resume Harness SDK

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

Version 0.2 adds a typed application workflow. Authenticate as above, install the
skills below, and ask Codex, Claude Code, or another harness to use
`resume-harness-apply`. The harness uses its own browser/computer-use tools.

```sh
resume-harness application-jobs --page 1 --page-size 50
resume-harness application-context 42
resume-harness application-prompt 42
resume-harness application-questions --job-id 42 --status unanswered
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
    jobs = list(harness.iter_application_jobs())
    if jobs:
        job_id = jobs[0]["jobId"]
        context = harness.application_context(job_id)
        # Give context["prompt"] to your browser/computer-use agent.
        # Record a question actually encountered on this employer's form:
        question = harness.record_application_question(
            "Have you previously worked for this employer?",
            job_id=job_id,
            context="Use the exact employer name and timeframe from the live form.",
        )
        # Ask the user. Continue ONLY after they provide/confirm the answer:
        user_answer = input("Your answer to the employer's question: ")
        harness.answer_application_question(
            question["id"], user_answer,
            revision=question["revision"], user_confirmed=True,
        )
        context = harness.application_context(job_id)
```

For common personal fields, read `get_application_profile()` and pass only the
user-confirmed changes to `update_application_profile(changes,
revision=snapshot["revision"], user_confirmed=True)`. Keys use camelCase; an
empty string clears an answer, omitted fields are preserved, and null/unknown
fields are rejected. These are application answers, not edits to resume evidence.

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
the token to an employer or arbitrary returned URL. The full prompt instructs
the agent to fill and verify the form, collect missing answers, and stop before
final submission or consent. Job approval does not itself authorize submission.
The queue is live and has no claims/leases; coordinate agents to avoid duplicates.

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
The installer does not change your agent configuration or install an agent.
Directory conventions: [Claude Code](https://github.com/anthropics/claude-code),
[pi skills](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md).

## CLI and errors

`resume-harness --help` lists commands. `context 42`, `jobs --board shortlist`,
`pull --limit 25`, `discover`, `tailor 42`, `runs`, `run RUN_ID`, and `wait RUN_ID` emit
JSON. `validate 42 --draft draft.json --revision REVISION` checks a local draft;
`submit` accepts the same arguments plus `--agent`. Use `render VERSION_ID` and
`download VERSION_ID --output resume.pdf` for PDFs. Downloads refuse overwrite.

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
