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

## Agent skills

The wheel includes `resume-harness-sdk` (write integration code and retrieve
information) and `resume-harness-tailor` (evidence-backed external authoring).
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
