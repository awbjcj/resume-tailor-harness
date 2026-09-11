# Résumé Tailor Harness

[![CI](https://github.com/awbjcj/resume-tailor-harness/actions/workflows/ci-main.yml/badge.svg)](https://github.com/awbjcj/resume-tailor-harness/actions/workflows/ci-main.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)

[English](README.md) | [简体中文](README.zh-CN.md)

Résumé Tailor Harness supports the full job-application workflow. It gathers job
posts from connectors, LinkedIn, or pasted descriptions; scores them against a
**fact-locked** profile of your experience; tailors a resume; drafts a matching
cover letter; renders both to PDF; and tracks each application in a
workspace-scoped SQLite database. Use it as a CLI, a local web app, or a hosted
multi-user service.

**Fact-lock** requires every tailored-resume bullet to trace back to a fact you
provided. Agents can draft, reframe, and critique. Deterministic control-flow
gates decide what can reach a saved document. [The harness](#the-harness)
explains those safeguards.

_The screenshots use a disposable demo workspace with fictional companies and
jobs._

## System architecture

The React frontend and CLI are thin entry points over the same use-case service
layer. Those services coordinate bounded agents, deterministic fact-lock gates,
workspace-scoped persistence, external integrations, and Typst rendering. In
hosted mode, the same shape runs with authenticated, tenant-confined workspaces;
every user-influenced public fetch crosses the validated outbound gateway.

![Résumé Tailor Harness system architecture](docs/diagrams/system-architecture.svg)

[Open the self-contained architecture diagram](docs/diagrams/system-architecture.html).

---

## The harness

The repository combines six safeguards that make an open-ended writing task
trustworthy, repeatable, and easier to control.

### 1. Fact-lock protects every claim

Your resume and repositories are extracted into a **closed-schema** evidence
profile (`data/profile/facts.json`): every fact carries an id, and the extraction
schemas refuse fields they do not define, so a project source cannot quietly emit
employment or education history.

Every tailoring round is then judged by **three deterministic gates** that run
in-process, with no model involved:

| Gate               | Blocks the round when a draft…                       |
| ------------------ | ---------------------------------------------------- |
| `provenance`       | cites a fact id that does not resolve to a real fact |
| `skill-naming`     | claims a skill your profile does not establish       |
| `numeric-evidence` | states a number your evidence does not support       |

Those three names are **reserved**. Configuring a reviewer with one of them is a
startup error, so editing the roster cannot shadow a gate. Gates and LLM
critiques flow through one verdict constructor
(`tailor/verdict.py::aggregate`), so "what makes a round pass" has exactly one
definition, and any failed gate blocks the round no matter how well it scored.

Cover letters use the same deterministic provenance gate. They do not use a
reviewer panel.

### 2. Skill-concentrated tailoring

A task agent belongs to a stable **agent family** such as job analysis, resume
authoring, resume review, cover letter, interview, career lab, internal profile,
or sponsorship research. Each agent uses **exactly one** approved procedure.

Those procedures are local `SKILL.md` files resolved through a root-confined,
**SHA-256-verified registry** (`career_skills/registry.py`) against the pinned
manifest in `skills-lock.json`. The model never chooses a path: it names a
capability, and the registry returns one immutable `SkillRef` (name, version,
digest, family). If the file was edited, symlinked, or points outside the skill
root, that capability is **disabled**. The system does not load altered text.
The resolved ref is stored with every artifact and turn it influenced, so any
output can be traced to the exact procedure bytes that produced it.

### 3. Bounded, read-only tool loops

Source Scout, Profile Coach, sponsorship research, and Career Lab use
**read-only** tools inside their loops: search, probe, and inspect. Deterministic
services write data after the loop and require your approval. The app checks tool
results again before presenting them as validated. Scout _proposes_ sources;
Coach _drafts_ notes that you edit before saving; Career Lab produces drafts
only. It cannot apply, upload, send, or update your profile.

### 4. Least-privilege prompting

Reviewer context is scoped by permission:

- **Gate reviewers** see the draft, the job description, and _only the profile
  facts that draft actually cites_.
- **Advisory reviewers** (style, impact, formatting) see no raw profile at all.
- Every third-party job description is wrapped in explicit untrusted-content
  delimiters, so a JD carrying "ignore your instructions" is data, not policy.
- A critique with the wrong reviewer identity is rejected. A merged advisory
  panel must cover its configured roster exactly, with no dropped or duplicated
  reviewers.

### 5. Cost control expressed as control flow

The reviewer panel is the expensive part, so the harness spends it carefully:

- Mechanically provable gates run **before** the paid panel, so a citation error
  reaches the reviser in the same round and avoids another premium fact-check
  round.
- A round that fails **only** on provenance earns a **free retry** and does not
  consume one of the `max_rounds` quality passes.
- Each revision starts from the **best gate-clean round**. A bad revision cannot
  become the base for the next.
- A score regression ends the loop early and avoids another paid round.
- Three model tiers (`CHEAP_MODEL`, `MID_MODEL`, `PREMIUM_MODEL`) are
  **provider-prefixed**. Cheap extraction can run on Gemini while the writer
  stays on Claude, and an unused provider SDK is never imported.

### 6. Durable runs and custody

Long operations are background **runs** with a durable event log: Server-Sent
Events are resumable, cancellation is cooperative, and terminal outcomes land in
an idempotent history, so a dropped browser connection cannot erase a result. In
hosted mode, each user gets an isolated workspace with its own database, corpus,
secrets, and renders. Every user-influenced fetch goes through a
DNS-rebinding-resistant egress gateway that validates each redirect and pins the
address it validated.

---

## How it works

Jobs flow through a funnel. Each stage has one command that advances it, and you
make the decision at two points. The two document-producing stages use the
deterministic gates from [The harness](#1-fact-lock-protects-every-claim) before
they save an artifact.

![Fact-locked resume lifecycle](docs/diagrams/resume-lifecycle.svg)

[Open the self-contained lifecycle diagram](docs/diagrams/resume-lifecycle.html).

| Stage            | Command                      | What happens                                                                                                                                                                    |
| ---------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Ingest**       | `pull` / `scrape` / `addjob` | Raw jobs land in the DB (deduped by URL or JD text). `pull` runs every enabled job-board connector; `scrape` drives LinkedIn; `addjob` takes one by hand.                       |
| **Discover**     | `discover`                   | Agents extract structured criteria, apply hard filters, score fit, and move eligible jobs to `shortlisted`.                                                                      |
| **👤 Approve**   | web app or `approve`         | The cost gate: you approve only the jobs worth paying to tailor.                                                                                                                |
| **Tailor**       | `tailor`                     | A writer agent drafts a fact-locked resume; a reviewer panel critiques and a reviser loops until it passes.                                                                     |
| **Cover letter** | `cover-letter`               | Drafts a fact-locked cover letter per job, gated by a deterministic provenance check, and renders it to PDF.                                                                    |
| **Render**       | `render`                     | A chosen resume version becomes a PDF in `output/`.                                                                                                                             |
| **👤 Track**     | web app / `sync-status`      | Record dated application events, outcomes, reflections, and offer details; export calendars/CSV, or let `sync-status` read Gmail and **propose** status moves for you to apply. |

### What it looks like

Every job in the board opens into one detail view with a fit score, requested
skills, and one tab for each stage:

![Job detail: fit score and skill match](docs/screenshots/job-detail.png)

**Ingest.** `pull` runs the connectors you've enabled; `+ Add URL` and
`Import file…` (top bar) take one job by hand. Manage boards at
**Settings → Sources** (`/settings/sources`):

![Sources: connectors and boards feeding the pull pipeline](docs/screenshots/sources.png)

**Discover.** Extraction and filtering land on the **Triage** page
(`/triage`). Clear the raw and rejected backlog before anything reaches the
shortlist:

![Triage: clear the raw and rejected backlog](docs/screenshots/triage.png)

**👤 Approve.** The **Shortlist** page (`/shortlist`) is the cost gate.
Review scored jobs and approve only what is worth paying to tailor:

![Shortlist: approve the jobs worth tailoring](docs/screenshots/shortlist.png)

**Tailor.** Open a job → **Resumes** tab to see each round's score,
fact-check status, and PDF render/revise actions:

![Resumes tab: tailored version, score, and fact-check status](docs/screenshots/resumes-tab.png)

**Cover letter.** Open a job → **Cover letters** tab for the fact-locked
draft, its provenance check, and a **Generate another** option:

![Cover letters tab: fact-locked draft and revision](docs/screenshots/cover-letters-tab.png)

**Render.** Rendered PDFs show up on the **Pipeline** board (`/pipeline`)
under their own stage, alongside every other stage in flight:

![Pipeline: every job by stage, including rendered PDFs](docs/screenshots/pipeline.png)

**👤 Track.** Open a job → **Tracking** tab to set application status and log
the complete timeline: submission, screening and interview rounds, outcomes,
reflections, offer details, and custom events. Dated events can be downloaded
as calendar files, while `sync-status` can propose moves from Gmail:

![Tracking tab: application status and notes](docs/screenshots/tracking-tab.png)

---

## Prerequisites

Choose one setup path:

- For containers, install Docker Engine with the Compose plugin. Docker Desktop
  includes both.
- For native development, install **[uv](https://docs.astral.sh/uv/)** and
  **Node.js 22+** with npm. `uv` manages Python 3.13 for the project.

AI-powered operations need an LLM provider key. Discover, tailor, and
cover-letter steps default to **Claude**, so an Anthropic key is enough to
begin. OpenAI, Google Gemini, and DeepSeek are also supported. The app can start
without a key, letting you configure one in the web UI. See
[LLM providers](#env--secrets-and-models).

Optional integrations:

- A **GitHub token** enriches your profile from repositories.
- A **burner LinkedIn account** is needed only for `scrape`.
- Job-board connector keys enable `pull` for sources such as
  [Adzuna API](https://developer.adzuna.com/). Greenhouse and RemoteOK need no key.
- Gmail OAuth credentials enable `sync-status`, scheduled sync,
  reminders, and email drafts. See [Gmail setup](#gmail-setup-for-sync-status-sync-reminders-and-email-drafts).

---

## Run with Docker

Docker builds the frontend and API into one image, stores application data in a
named volume, and publishes the app only on this computer's loopback interface.

### Configure once

Copy the safe template, then set an LLM provider key (for example,
`ANTHROPIC_API_KEY`) if you want AI-powered operations. The app can still start
without a key so you can finish configuration from its UI.

```powershell
Copy-Item .env.example .env
notepad .env
```

`RESUME_TAILOR_HARNESS_PORT` is optional when port `8000` is busy. The `.env`
file never enters the built image. Do not enable the H-1B variables in `.env`
just to use the bundled service; the optional Compose stack supplies its private
container URL at runtime.

### Start the app

```bash
docker compose up --build
```

Open <http://localhost:8000>. Stop it with `Ctrl+C` and later restart with
`docker compose up`. `docker compose down` removes the container and network
but retains your named data volume. Use `docker compose down --volumes` only
when you intentionally want to erase local application and H-1B cache data.
Browser-backed connectors are disabled in the image; use the native setup when
you need LinkedIn or another browser-driven source.

### Start with the optional H-1B service

The repository pins the companion service as a submodule and builds it with its
frozen dependency lock, so the combined stack uses a known source revision.
Clone with `--recurse-submodules`, or initialize it once in an existing clone:

```bash
git submodule update --init --recursive
docker compose -f compose.yaml -f compose.h1b.yaml --profile h1b up --build
```

This starts the application and the H-1B MCP service together. The MCP endpoint
is private to Docker's network; only the application remains reachable at
<http://localhost:8000>. Both data stores use named volumes and survive normal
stops/restarts. Historical H-1B data remains advisory evidence, not proof of a
company's current sponsorship policy.

### Windows quick start

Install and start [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
(the default WSL 2 backend works for most users), then verify it from
PowerShell:

```powershell
docker version
docker compose version
```

Install Git for Windows too only if you plan to use `-WithH1B`, because that
mode initializes the pinned service submodule on first use.

The included PowerShell launcher creates a missing `.env`, checks Docker
Desktop, initializes the optional submodule when needed, and preserves data on
stop:

```powershell
.\scripts\windows\Start-ResumeTailor.cmd -Detach
.\scripts\windows\Start-ResumeTailor.cmd -WithH1B -Detach
.\scripts\windows\Start-ResumeTailor.cmd -WithH1B -Status
.\scripts\windows\Start-ResumeTailor.cmd -WithH1B -Stop
```

`-WithH1B` is optional; omit it for the smaller default image. Add `-Port 8080`
to either start command when you need a different local port. The `.cmd`
launcher applies an execution-policy bypass only to the child PowerShell process;
you may also call the `.ps1` file directly from an already-configured shell.

To build and run the image without Compose:

```bash
docker build -t resume-tailor-harness .
docker run --name resume-tailor-harness --init --restart unless-stopped \
  -e APP_MODE=local \
  -p 127.0.0.1:8000:8000 \
  -v resume-tailor-harness-data:/app/data \
  resume-tailor-harness
```

PowerShell accepts the same command with backticks instead of backslashes, or
as one line. Add `--env-file .env` after creating `.env` if you want to inject
provider keys at container startup; keys can also be saved from the web UI.

The image defaults to auth-free local mode. For an internet-facing multi-user
deployment, set `APP_MODE=hosted` and follow [Hosted multi-user server](#hosted-multi-user-server); hosted mode requires credentials and a canonical HTTPS URL.

## Native setup (Windows, macOS, and Linux)

The bootstrap command installs locked Python and frontend dependencies. It also
creates missing local configuration files without overwriting your edits:

```bash
uv run --no-project scripts/bootstrap.py
uv run resume-tailor-harness setup                 # optional guided configuration
uv run python scripts/dev.py              # API + frontend; Ctrl+C stops both
```

Open <http://localhost:5173>. The same commands work in PowerShell, Command
Prompt, and POSIX shells. If you use `make`, `make setup` and `make dev` are
short aliases. Pass `--browser` to the bootstrap command only when you need
browser-backed job sources such as LinkedIn.

`resume-tailor-harness setup` walks through secrets, search criteria, and connectors and
writes `.env` plus `config/*.yaml`. You can instead edit the files created from
the checked-in examples.

Everything else (the SQLite database, the `output/` and `data/` folders) is
created automatically on first run.

---

## Tools for the job search

These tools use the same fact-lock profile, verified skill registry, read-only
tool loops, and durable run history. They help with the repeat work of a job
search:

| Tool                     | How it helps                                                                                       |
| ------------------------ | -------------------------------------------------------------------------------------------------- |
| **Profile Coach**        | Captures evidence you have not written down. It asks one question at a time and drafts only what you said. |
| **Mock Interviews**      | Lets you rehearse for a specific tailored role and gives you a scored debrief.                    |
| **Career Lab**           | Supports negotiation prep, career pivots, and portfolio writing. Each turn uses one verified skill, and every output stays a draft. |
| **Match-gap**            | Ranks skills your target jobs demand that your profile does not yet show.                         |
| **Sponsorship evidence** | Uses historical filings as a research signal. It does not promise current sponsorship.            |
| **Company intelligence** | Creates a cited employer brief when you request one.                                              |
| **Application timeline** | Keeps rounds, outcomes, and deadlines in one dataset that you can export as CSV or a calendar.   |
| **Gmail sync**           | Reads your inbox and proposes status updates for you to approve.                                  |
| **Analytics**            | Shows which sources and fit bands lead to later-stage progress.                                   |

### Career coaching: Profile Coach, Mock Interviews, and Career Lab

The sidebar has three coaching tools, each for a different point in the job
search.

**Profile Coach** (`/coach`) reviews your current fact-lock profile, asks one
focused question at a time about outcomes, scope, or project evidence you may
have left out, and drafts only claims grounded in what you actually answered:

![Profile Coach: guided evidence discovery](docs/screenshots/profile-coach.png)

**Mock Interviews** (`/interview`) runs a focused rehearsal against a
specific tailored role, then turns the conversation into a scored debrief you
can act on:

![Mock Interviews: rehearse for a tailored role](docs/screenshots/mock-interview.png)

**Career Lab** (`/career-lab`) is a draft workspace also available through
the `career-lab` CLI command and the `/api/career-lab` REST resources.
It routes each turn to one verified local career skill, keeps one active session
per workspace, streams recoverable runs, and supports end, archive, unarchive,
and delete actions. Every output remains a draft. It cannot apply, upload, send,
or update a profile.

![Career Lab: one verified skill at a time, with draft-only output](docs/screenshots/career-lab.png)

```bash
uv run resume-tailor-harness career-lab "Prepare negotiation points" \
  --skill salary-negotiation-prep --offer-application-id 7
```

H-1B enrichment is optional historical evidence for jobs whose search config
requires sponsorship research and whose posting signal is silent. Set
`H1B_MCP_ENABLED=true` and configure either a local `stdio` command or a
credential-free Streamable HTTP URL in `.env.example`. Do not configure both.
The app exposes only these read-only MCP tools: `h1b_get_company_stats`,
`h1b_search_h1b_jobs`, and `h1b_get_available_data`. Historical filings are
advisory evidence. They cannot confirm current sponsorship or employer policy,
change a posting signal, or hard-reject a job. Review them per job from the
**Sponsorship** tab in the job detail view:

![Sponsorship tab: historical H-1B filing evidence for one company](docs/screenshots/sponsorship-tab.png)

For local development, `make dev` starts only the API and Vite frontend, so a
fresh clone has no H-1B service process. After `git submodule update --init
--recursive`, `make full-stack` also starts the optional bundled
`h1b-job-search-mcp` server. That launcher uses
`http://127.0.0.1:8001/mcp` for the API's Streamable HTTP connection, so no
manual MCP command or URL is needed. Run `make stack-health` after startup to
check both HTTP health endpoints and the MCP handshake/tool allowlist.

For the Docker equivalent, use the optional `h1b` profile in
[Run with Docker](#run-with-docker). Do not use `localhost` for that profile's
MCP URL: inside a container it would refer to the application container rather
than the companion service.

### Application workspace and company research

The **Applications** page (`/applications`) shows active applications from one
timeline dataset. You can search and sort the grid, compare repeated technical
rounds, and export either a readable wide grid or a lossless event-level CSV.
**Analytics** (`/analytics`) uses the same dataset for stage flows, cycle
times, active-pipeline lanes, and offer comparisons. You can also download
upcoming events together as an `.ics` calendar.

Each job's **Research** tab separates employer evidence from sponsorship
evidence. **Company intelligence** creates a cited brief covering strategy,
recent moves, engineering culture, challenges, and competitive position. You
trigger each refresh. Only citations present in the research output survive
validation, stale evidence stays visibly marked, and jobs at the same normalized
company share the saved dossier.

You can save Triage, Shortlist, and Pipeline filters as named workspace views.
The notifications menu retains terminal success, failure, and cancellation
outcomes for background runs. The Dashboard summarizes practice-score trends,
open source failures, and the action queues.

---

## Deployment and integrations

### Hosted multi-user server

`resume-tailor-harness serve` is an auth-free local application by default: it binds to
loopback, reuses the existing administrator workspace (or creates a `local`
workspace on first boot), and does not require account credentials. To expose a
server or enable multiple users, opt into hosted mode and seed the first
administrator before its first boot:

```bash
uv run resume-tailor-harness serve --mode hosted --host 0.0.0.0
```

```env
AUTH_USERNAME=owner
AUTH_PASSWORD_HASH=<output of `uv run resume-tailor-harness hash-password`>
SESSION_SECRET=<long random value>
```

After signing in, create a single-use invite on the **Admin** page or with
`resume-tailor-harness admin invite`. Members register at `/register`; each receives a
separate database, profile corpus, configuration, secrets, output, and run
history. Administrators manage recurring USD-cost allowances, durable credits,
effective-dated LLM rates, active-job caps, and concurrent-run caps. Token usage
remains available as shared/BYOK analytics but does not control quotas after the
[cost quota rollout](docs/cost-quotas.md) reaches enforcement. Members manage
their own keys, tokens, password, and
workspace export in the web UI. The remote member workflow is web-first; the
local domain CLI can select an existing workspace with `--user USERNAME`.

`REGISTRATION_MODE` (`invite` by default, or `closed`/`open`) controls whether
an invite is required at all. Every administrator, free member, and subscriber
can use the platform's shared LLM keys. Configure those keys as Railway
environment variables; they are selected before a workspace key. Once the
applicable account or platform allowance is exhausted, calls automatically use
that user's key for the provider when one is configured.
`GLOBAL_DAILY_SIGNUP_LIMIT` and `GLOBAL_WEEKLY_TOKEN_BUDGET` cap total
verification emails and total shared-key spend platform-wide, regardless of
how many accounts exist. See [Deploying to Railway](docs/deploy-railway.md)
for the full variable list and recommended production posture.

### Gmail setup (for `sync-status`, sync, reminders, and email drafts)

Gmail powers the CLI's `sync-status`, plus (in the API/web app) scheduled
background inbox sync, stale-application follow-up reminders, and the
email-draft writer. It only ever **reads** mail (readonly scope) and
**creates drafts** (compose scope). It never sends anything. There's no
password in `.env`; it authenticates via a Google OAuth client, and which
_type_ of client you create depends on how you run the app:

**CLI, single machine:** an OAuth **Desktop app** client stored as a file:

1. In the [Google Cloud console](https://console.cloud.google.com/), create (or
   reuse) a project, enable the **Gmail API**, and create an **OAuth client ID**
   of type _Desktop app_.
2. Download the client-secret JSON and save it as `config/gmail_credentials.json`.
3. The first `sync-status` run opens a browser consent screen once; the granted
   token is cached to `data/gmail_token.json` (git-ignored) and reused after that.

**Web app / API server** (used by a Railway deployment): an OAuth **Web
application** client configured through environment variables instead of a file:

1. Create an OAuth client ID of type _Web application_ (the same Cloud console
   project as above is fine). Add an **authorized redirect URI** of
   `<your-domain>/api/gmail/callback`, such as `http://localhost:8000/api/gmail/callback`
   for local `resume-tailor-harness serve`, or your Railway domain for a cloud deploy
   (see [Deploying to Railway](docs/deploy-railway.md#gmail-oauth-optional)).
2. Set `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` in `.env` (or
   as platform environment variables on Railway). This is the **platform
   client** every workspace connects through by default; any signed-in user
   can instead paste their own client id/secret under Settings → Keys, which
   overrides the platform client for their workspace only.
3. Sign in to the web app, open **Settings → Keys**, and click **Connect
   Gmail** on the Gmail card to run the consent flow. The granted token is
   stored per-workspace (never shared across users).

Either way, while your OAuth consent screen is in **Testing** publishing
status (the default), add every Gmail address that will connect as a **test
user** in the Cloud console. Google caps testing apps at 100 users and
rejects sign-in for anyone not on that list.

Skip this if you prefer to track statuses by hand in the web app. Everything
else works without it.

All commands below are shown as `uv run resume-tailor-harness …`. If you'd rather not
prefix every call, activate the venv first (`source .venv/bin/activate`, or
`.venv\Scripts\Activate.ps1` on Windows) and drop the `uv run`.

---

## Quickstart

```bash
# 1. Build your fact-lock profile from your resume (+ optional GitHub)
uv run resume-tailor-harness profile build

# 2. Get some jobs into the pipeline (pick one)
uv run resume-tailor-harness pull --limit 10            # job-board connectors, or…
uv run resume-tailor-harness scrape --limit 10          # LinkedIn, or…
uv run resume-tailor-harness addjob --company "Acme" --title "Backend Engineer" --jd-file jd.txt

# 3. Score them against your profile and your search criteria
uv run resume-tailor-harness discover
uv run resume-tailor-harness match-gap                 # optional: see missing high-demand skills

# 4. Review the shortlist and approve the keepers in the web app
make dev                                # http://localhost:5173

# 5. Tailor every approved job, and draft matching cover letters
uv run resume-tailor-harness tailor --approved
uv run resume-tailor-harness cover-letter --approved

# 6. Render a specific resume version to PDF (id shown in the web app)
uv run resume-tailor-harness render 12

# 7. Track submissions back in the web app
make dev                                # http://localhost:5173

# 8. Later, let Gmail propose status updates (review first, then apply)
uv run resume-tailor-harness sync-status               # lists proposals only
uv run resume-tailor-harness sync-status --apply        # applies them
```

---

## Command reference

Run `uv run resume-tailor-harness --help` for the full command list. For one
command, run `… <command> --help`. Every command accepts `--db-url` for a
different database, which is useful for testing.

### `profile build`: create your fact-lock profile

Reads your resume (and GitHub, if configured) into `data/profile/facts.json`.
This file is the **ground truth** every later step is allowed to draw from.

```bash
uv run resume-tailor-harness profile build [--sources config/profile_sources.yaml] [--out data/profile/facts.json] [--refresh]
```

`--refresh` rebuilds the file and **discards any manual edits**. Without it, the
command refuses to overwrite an existing `facts.json`.

### `addjob`: add one job by hand

The job description is read from `--jd-file`, or from stdin if you omit it.

```bash
uv run resume-tailor-harness addjob --company "Acme" --title "Backend Engineer" --url "https://…" --jd-file jd.txt
```

Duplicates (same URL or identical JD text) are detected and skipped.

### `scrape`: pull jobs from LinkedIn

Searches LinkedIn using your `search.yaml`, then ingests matching posts as raw
jobs. **First run:** a real browser window opens. Log in to your burner account
by hand _once_. The session is saved to `.linkedin_profile/` and reused after
that.

```bash
uv run resume-tailor-harness scrape [--search config/search.yaml] [--limit 25]
```

`--limit` caps how many postings are processed this run (be a polite scraper).

### `pull`: pull jobs from job-board connectors

Runs every connector enabled in `connectors.yaml`, dedupes results into `raw`
jobs, and prints a per-source count. When a higher-priority (canonical) source
re-finds a job already in the DB from an aggregator, it **upgrades** the stored
URL and JD text in place. The pull summary shows `+N added, N upgraded`.
Secrets (such as Adzuna keys) come from `.env`;
which boards/sources to hit come from `connectors.yaml`.

| Connector    | What it needs                                                                                     |
| ------------ | ------------------------------------------------------------------------------------------------- |
| `greenhouse` | Board tokens in `connectors.yaml`                                                                 |
| `lever`      | Board slugs in `connectors.yaml`                                                                  |
| `adzuna`     | `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` in `.env`                                                      |
| `remoteok`   | Nothing; it uses an open API                                                                      |
| `linkedin`   | Burner credentials in `.env` (same as `scrape`)                                                   |
| `companies`  | Careers URLs in `connectors.yaml`. Detects Greenhouse, Lever, Ashby, Workday, Tesla, and Google |

```bash
uv run resume-tailor-harness pull [--connectors config/connectors.yaml] [--search config/search.yaml] [--limit 25]
```

`--limit` caps postings **per connector** this run. If `config/connectors.yaml`
is missing, the command tells you to copy it from the example first.

### `sources`: connector run history

Shows when each connector last ran, how many jobs it added, and its last error,
if any. Use it as a quick health check after `pull`.

```bash
uv run resume-tailor-harness sources
```

### `discover`: extract, filter, and score

Runs the funnel over every `raw` job already in the database. It extracts
structured criteria, removes jobs that fail hard filters, and assigns each
remaining job a fit score from 0 to 100 with a rationale. Eligible jobs move to
`shortlisted`.

```bash
uv run resume-tailor-harness discover [--search config/search.yaml] [--facts data/profile/facts.json]
```

### `match-gap`: target-job skills your profile does not show

Compares the `must_have_skills` of every job that survived discovery
(`shortlisted` / `approved` / `tailored` / `rendered`) against your profile's
skill names and aliases. Gaps are ranked by how many target jobs demand them.
This is read-only: it never edits `facts.json`. The same view is at
**Match-gap** (`/match-gap`) in the web app:

![Match-gap: skills your target jobs demand that your profile does not show](docs/screenshots/match-gap.png)

```bash
uv run resume-tailor-harness match-gap                 # aggregate, most-demanded first
uv run resume-tailor-harness match-gap --job-id 7      # gaps for one target job
uv run resume-tailor-harness match-gap --llm           # optional synonym pass, e.g. k8s/Kubernetes
```

### `approve`: the cost gate (CLI alternative to the web app)

Marks a shortlisted job `approved` so it's eligible for tailoring.

```bash
uv run resume-tailor-harness approve 7
```

### `tailor`: draft and review loop

Tailors one job (`--job-id`) or every approved job (`--approved`). Each round is
saved as a `ResumeVersion`. The three deterministic gates and the reviewer panel
judge the round. The loop revises until a draft passes or it uses all
`max_rounds` quality passes.

The **fact-check** reviewer, `provenance`, `skill-naming`, and
`numeric-evidence` are hard gates. A round that fails _only_ on provenance gets
a free retry without spending a quality pass. Optional `config/style_guide.md`
prose is appended below the fixed fact-lock rules for the writer, reviser, and
reviewers. It controls how resumes are written, never what is claimed. See
[The harness](#the-harness) for the full control flow.

```bash
uv run resume-tailor-harness tailor --approved
uv run resume-tailor-harness tailor --job-id 7
```

### `cover-letter`: draft a fact-locked cover letter

Writes a cover letter for one job (`--job-id`) or every approved job
(`--approved`), then renders it to a PDF in `output/`. The writer uses only your
`facts.json`. A **deterministic provenance gate** checks that every paragraph
cites real fact IDs and loops a reviser until the draft is clean. If it does not
pass, the app records `fact_check_passed=False` so you know not to send it. This
workflow uses a deterministic gate without a reviewer panel.

```bash
uv run resume-tailor-harness cover-letter --approved
uv run resume-tailor-harness cover-letter --job-id 7
```

### `render`: version to PDF

Renders a stored resume version (by ID) through the Typst template into
`output/`. Filenames are unique per version, so re-rendering does not overwrite
an earlier PDF.

```bash
uv run resume-tailor-harness render 12 [--config config/render.yaml]
```

### Web app: visual boards

The web app runs the FastAPI backend and React frontend with Shortlist,
Pipeline, Triage, Applications, Analytics, and Match-gap views. Use it to
approve shortlisted jobs, inspect rendered artifacts, maintain application
timelines, save board views, and prune stale jobs. It opens on the **Dashboard**
(`/`) with daily counts by stage, practice and source-health insights, and links
to work that needs attention:

![Dashboard: daily operations at a glance](docs/screenshots/dashboard.png)

**Analytics** (`/analytics`) shows which sources and fit-score bands convert to
interviews and offers, plus stage flows, cycle times, the active application
timeline, and compensation comparisons:

![Analytics: conversion funnel by source and fit band](docs/screenshots/analytics.png)

```bash
make dev                                # http://localhost:5173
```

### `sync-status`: let Gmail propose status updates

Scans recent inbox mail (read-only), matches each message to a tracked
application by company, classifies it (rejection / interview / assessment /
offer) with deterministic rules plus an optional cheap-LLM fallback, and
**proposes** forward-only status moves. Nothing changes until you re-run with
`--apply`. Statuses are never changed silently. Requires
[Gmail setup](#gmail-setup-for-sync-status-sync-reminders-and-email-drafts) (the
CLI, Desktop-app path).

```bash
uv run resume-tailor-harness sync-status                 # list proposals only
uv run resume-tailor-harness sync-status --apply         # apply them
uv run resume-tailor-harness sync-status --max-results 100
```

---

## API server

The pipeline is also available over HTTP for the React frontend and other API
clients:

```bash
uv run resume-tailor-harness serve                       # http://127.0.0.1:8000
uv run resume-tailor-harness serve --mode hosted --host 0.0.0.0 --port 8080
```

Local mode skips account authentication, always activates the default workspace,
and refuses non-loopback binds. Hosted mode enables login, bearer/PAT checks,
tenant selection, registration, and isolated user workspaces. The container
defaults to local mode. It switches to hosted mode when `APP_MODE=hosted` is set
or when hosted-only settings such as `APP_BASE_URL` are present.

- Interactive docs at `/docs`; the OpenAPI schema at `/openapi.json`.
- The committed contract the frontend consumes lives in `contracts/`
  (`openapi.json` + generated `ts/api.ts`); regenerate with
  `bash scripts/gen_ts_client.sh` after any schema change.
- Long operations return a **run** you watch via
  `GET /api/runs/{id}/events` (Server-Sent Events) or poll at
  `GET /api/runs/{id}`. Terminal outcomes are also recorded in the durable
  `/api/run-completions` history so a dropped browser connection cannot erase
  the result.
- Application events live under `/api/jobs/{job_id}/events`; the cross-job
  projection is `/api/applications`, with wide/long CSV and purpose-bound ICS
  downloads. Saved board views use `/api/board-views`, and explicit company
  research uses `/api/jobs/{job_id}/company-intelligence/refreshes`.
- In hosted mode, configure account credentials/PATs for API access and set
  `CORS_ORIGINS` (comma-separated) for a separate frontend dev server. Local
  mode intentionally ignores account and API authentication settings.

Gmail sync (`POST /api/gmail/sync`), connect/status/disconnect
(`/api/gmail/connect|status|token`), and email drafts are exposed over HTTP.
Deferred (not yet exposed over HTTP): `profile build` and LinkedIn `scrape`.

---

## Configuration

### `.env`: secrets and models

Copy `.env.example` to `.env`. The app loads it automatically. The example
contains every environment-backed application setting with safe local defaults. See the
[complete environment configuration reference](docs/configuration.md) for
accepted values, bounds, hosted/Docker overrides, and integration-specific
requirements.

#### Choosing an LLM provider

Every LLM call uses one of three model tiers: `CHEAP_MODEL`, `MID_MODEL`, and
`PREMIUM_MODEL`. They default to Claude Haiku, Sonnet, and Opus. A model ID can
carry a provider prefix. An unprefixed ID uses Anthropic, while an `openai:`,
`gemini:`, or `deepseek:` prefix routes that tier to another provider. Each tier
uses its provider's key, so you can mix providers freely:

```bash
CHEAP_MODEL=gemini:gemini-3.5-flash-lite # cheap extract/fit/relevance on Gemini
MID_MODEL=deepseek:deepseek-v4-flash    # reviewers / cover-letter reviser on DeepSeek
PREMIUM_MODEL=claude-opus-5             # bare id → Anthropic for the tailor writer
```

Set only the keys for the providers you actually use; a provider's SDK is loaded
lazily, so a Claude-only run never touches the OpenAI or Gemini libraries.

> **Gmail** authenticates via `config/gmail_credentials.json` for the CLI only;
> the API/web app instead uses the `GOOGLE_OAUTH_CLIENT_ID`/`_SECRET` env vars
> above. See [Gmail setup](#gmail-setup-for-sync-status-sync-reminders-and-email-drafts).

### `config/*.yaml`

| File                   | Controls                                                                                                                                                                                                                                                                   |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `profile_sources.yaml` | Path to your resume and your GitHub username.                                                                                                                                                                                                                              |
| `search.yaml`          | Keywords, titles, locations, and **hard filters** (salary, years of experience, remote policy, sponsorship).                                                                                                                                                               |
| `connectors.yaml`      | The job-board connectors that `pull` runs and their parameters: Greenhouse board tokens, Lever slugs, Adzuna country, RemoteOK, LinkedIn on/off, and `companies.urls` for direct ATS or portal URLs. It detects Greenhouse, Lever, Ashby, Workday, Tesla, and Google. Secrets stay in `.env`. |
| `review.yaml`          | The reviewer roster, their weights/model tiers, `max_rounds`, `score_threshold`, optional `length_budget` one-page guidance, and optional `style_guide_path`.                                                                                                              |
| `render.yaml`          | Typst `template_path` and the PDF `output_dir`.                                                                                                                                                                                                                            |
| `style_guide.md`       | Optional house-style prose appended to the resume tailor loop. Governs how resumes are written, never what is claimed. Missing or empty means no change.                                                                                                                   |

Each `*.yaml.example` is annotated. Copy it, then edit it.

The cover-letter and resume templates live in `templates/` (`cover_letter.typ`,
`resume.typ`) and can be edited directly. `config/gmail_credentials.json`
(CLI-only `sync-status`) is the one config file with no example. It is the
Desktop-app OAuth client secret you download from Google Cloud (see
[Gmail setup](#gmail-setup-for-sync-status-sync-reminders-and-email-drafts)).
The API/web app uses `GOOGLE_OAUTH_CLIENT_ID`/`_SECRET` in `.env` instead.

### Source priority

When the same job is seen by multiple connectors, a **canonical** source always
wins over an **aggregator** copy:

| Tier                            | Sources                                                                                        |
| ------------------------------- | ---------------------------------------------------------------------------------------------- |
| **Canonical** (higher priority) | `greenhouse`, `lever`, `ashby`, `workday`, `tesla`, `google`, `companies`, `url` (hand-pasted) |
| **Fallback** (lower priority)   | `adzuna`, `remoteok`, `linkedin`                                                               |

**First-seen wins** among equal-tier sources, preventing churn from same-tier
re-pulls.

**Upgrade, not drop.** If a canonical source re-finds a job previously ingested
from a fallback source, the stored posting fields (`url`, `jd_text`, `source`,
`title`, `location`) are upgraded in place, keeping the same `Job` id. Your
tailored resumes, cover letters, and application status are never touched.

Once a job's status has advanced past `raw`, only the canonical apply `url` is
updated (the JD text is frozen so a resume already tailored to it is not
silently re-based).

---

## Where things live

| Path                                                  | Contents                                                                                                                                                        |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `data/resume_tailor_harness.db`                       | All jobs, resume versions, cover letters, and applications (SQLite).                                                                                            |
| `data/profile/facts.json`                             | Your fact-lock profile.                                                                                                                                         |
| `data/connector_runs.json`                            | Per-connector run history that `sources` reads.                                                                                                                 |
| `data/gmail_token.json`                               | Cached Gmail OAuth token for CLI/local-mode `sync-status` (git-ignored). The API/web app stores each user's token inside their own workspace instead.           |
| `output/`                                             | Rendered resume **and** cover-letter PDFs (cover letters are suffixed `cl<id>`).                                                                                |
| `.linkedin_profile/`                                  | Cached LinkedIn browser session (git-ignored).                                                                                                                  |
| `config/gmail_credentials.json`                       | Your Gmail OAuth **Desktop app** client secret for CLI-only use (git-ignored; you provide it). The API/web app uses `GOOGLE_OAUTH_CLIENT_ID`/`_SECRET` instead. |
| `templates/resume.typ` / `templates/cover_letter.typ` | The Typst templates the renderers use.                                                                                                                          |

`data/`, `output/`, `.env`, `.linkedin_profile/`, and `config/gmail_credentials.json`
are all git-ignored.

---

## A note on scraping responsibly

`scrape` is built for **personal, low-volume** use against a **burner** account:
it drives a real logged-in browser, paces its requests deliberately, and caps
how much it pulls per run. Keep `--limit` modest and don't point it at an account
you care about. Manual `addjob` is always available if you'd rather skip scraping.

The `companies` connector's Workday backend issues one detail request per
surviving job listing. Keep the relevance filters in `search.yaml` tight so the
title-gate prunes the list before detail fetches begin.

---

## Development

```bash
uv run pytest              # run the full test suite
uv run pytest -k scraper   # run a subset
ruff check                 # lint
```

Tests are pure and offline. Agents and the browser are faked, so the suite needs
no API key and no network. Connector backends are tested against fixture JSON
payloads captured from real responses.

v1.5 keeps the tailor loop synchronous. Parallel reviewer panels and job-level
concurrency are deferred while this pass reduces cost through leaner prompts.

## Contributing

Contributions are welcome. See [CONTRIBUTING](.github/CONTRIBUTING.md) for local
setup and the checks your change must pass (`make verify`). Create your branch
from `dev` and open a PR into `dev`.

## Security

Found a vulnerability? Please report it privately. See the
[security policy](.github/SECURITY.md). Do not open a public issue for security
reports.

`docs/` also carries a self-audit of the public multi-user deployment:
[`resume-tailor-harness-threat-model.md`](docs/resume-tailor-harness-threat-model.md)
(trust boundaries, attacker model, prioritized threat table) and
[`security_best_practices_report.md`](docs/security_best_practices_report.md)
(findings with severity, evidence, and fixes). See [ADR-0008](docs/adr/0008-egress-gateway-tenant-storage-canonical-origin.md)
for the architectural response already shipped (SSRF-safe outbound gateway,
tenant-confined artifact downloads, configuration-only OAuth/cookie origin)
and the P0/P1 items still open.

## License

[MIT](LICENSE) © awbjcj
