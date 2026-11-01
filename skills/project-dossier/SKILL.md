---
name: project-dossier
description: Generate an evidence-backed project dossier markdown for the resume-tailor-harness profile corpus. Use when the user asks to create a project dossier, document a repository for their resume profile, or extract a project profile from the current repository.
---

# Project Dossier

Distill the current repository into one fact-locked markdown source that
resume-tailor-harness can ingest in `project` mode. Every claim must be verifiable from
the repository's code, documentation, tests, or git history.

## What survives ingestion

The dossier is read by a project-scoped extractor with a **closed** schema
(`ProjectDocFacts`, `extra="forbid"`): exactly one project record plus
evidenced skills. Prose that maps onto no field is dropped, so write toward
this contract:

| Field | Filled from |
| --- | --- |
| `name` | `# Project:` heading |
| `description` | `## Summary` |
| `role` | `Role:` line |
| `tech[]` | `## Tech stack` (load-bearing — see mechanic 2) |
| `highlights[]` | Architecture highlights, quantified outcomes, and each cited skill application; stored as independently addressable Bullet facts |
| `repo_url`, `url`, `homepage_url` | `Repository:` / `Live:` lines |
| `start`, `end` | `Timeline:` line, from `git log` |
| `skills{category: [name, aliases, context]}` | `## Skills demonstrated` |

Employment, job titles, education, and certifications are unreachable by
design. Writing them wastes space and produces a worse project record.

## Six mechanics that decide whether the dossier lands

**1. A skill's name is the whole match token.** `matrix.py` keys each row on
`normalize_skill(skill.name)` — the entire string, never split. The job
description side *is* split into atomic requirements, so the comparison is
atomic-requirement against whole-profile-name. Every extra word guarantees a
miss:

| Written as | Becomes the key | Matches a JD asking for Kubernetes? |
| --- | --- | --- |
| `Kubernetes (k8s)` | `kubernetes k8s` | never |
| `AWS (EC2, S3, Lambda)` | `aws ec2 s3 lambda` | never |
| `Kubernetes` + alias `k8s` | `kubernetes` | yes |

One atomic skill per entry, canonical name alone, synonyms in a separate
`Aliases:` field. Keep usage context and evidence outside the name.

**2. Keep technology coverage explicit.** List every evidenced technology in
`## Tech stack` using the same canonical name as its skill entry. The matrix
uses technology names, project highlight text, and explicit skill-to-example
links. Broader skills such as concurrency need their own explained examples;
they do not need to be forced into the tech stack.

**3. An omitted end date claims the project is current.** `_recency(None)`
returns `1.0` — full strength, no decay. Correct for live work, quietly false
for a project abandoned two years ago. Read the real dates:

```bash
git log --reverse --format=%as | head -1   # first commit
git log -1 --format=%as                    # last commit
```

Emit `Timeline: 2024-03 – present` for active work (end left open), and
`Timeline: 2023-01 – 2024-06` for dormant or archived work.

**4. Every example can become its own fact.** Project highlights and labeled
skill evidence are stored as independently citable Bullet facts with stable
source-derived ids. Keep each example self-contained, with its citation,
measurement scope, and attribution. Repeated text is one fact shared by its
supporting skills. Do not inflate one action into several achievements.

**5. Identity decides whether the file is read as a project at all.** The
`repo_url:` frontmatter key is the switch into project mode. Missing or
malformed, the file falls back to `default_mode(".md")` → **`literal`**, and
the resume extractor will try to read employment and education out of it — the
worst possible failure. The value must be a public `http(s)` URL with a path,
no embedded credentials, no `localhost` or private address. The block must
start at byte zero: `---` on line 1, no BOM, no blank line above it.

**6. No skill without demonstrated usage.** Every skill needs a usage summary
and at least one explained, cited application. Prefer multiple distinct examples
from implementation, tests, migrations, and operations. A dependency, unused
import, bare path, scaffold, or roadmap mention alone is insufficient. Code
presence establishes behavior, not personal authorship: use the stated role and
contribution history to distinguish the user's work from inherited code.

## Monorepos need distinct repository links

Projects merge on `repo_url` **before** name (`merge._find_project`), so N
dossiers carrying the same `Project.repo_url` collapse into one merged project
with the union of their tech and highlights — the exact outcome splitting was
meant to avoid. Separate the two identities:

- **Frontmatter `repo_url`** stays the canonical repository URL in every
  dossier. `sync-github` validates it against the repository and skips any file
  pointing elsewhere, so it cannot be changed.
- **Body `Repository:` line** carries a distinct deep link per project
  (`https://github.com/owner/repo/tree/main/packages/api`), which becomes that
  project's own `repo_url` and keeps the records separate.

Give each project a genuinely distinct `# Project:` name as well — name is the
fallback match key.

## Workflow

1. Confirm the repository root and inspect its canonical `origin` remote.
2. Decide the split: one coherent project → one dossier; a monorepo of
   genuinely separate deliverables → one dossier per project. Do not split a
   single system to inflate the count.
3. Read implementation files and tests before relying on README claims.
4. Use git history and shortlog for contribution role, commit-backed outcomes,
   and the first/last commit dates. Do not infer authorship from the working
   tree alone.
5. Draft the required structure below, citing repository-relative paths and
   commit hashes where they support architecture or quantified claims.
6. Build a skill evidence map: every claimed skill has a usage summary and
   cited examples attributable to the user's work. Every technology named in
   the summary or highlights also appears in `## Tech stack`. Seek distinct
   applications rather than stopping at the first citation.
7. Re-read every sentence and remove anything the repository cannot prove.

## Output contract

Write `<repo-name>-dossier.md` at the repository root, or at the location the
user requests. For a monorepo, write `<project-slug>-dossier.md` per project.
Start at byte zero with this frontmatter — `repo_url` is the stable identity
resume-tailor-harness uses to supersede an auto-harvested GitHub source:

```yaml
---
repo_url: <canonical HTTPS repository URL derived from git remote get-url origin>
repo_name: <repository directory name>
role: <sole author | maintainer | contributor, supported by git shortlog>
generated_at: <today, YYYY-MM-DD>
---
```

Frontmatter carries identity, not content — only `repo_url` is parsed
mechanically. Restate role and links in the body so the extractor reads them.

Then use exactly these sections.

### `# Project: <name>`

Give one line positioning what the project is and who it serves.

### `## Summary`

Write 3-6 sentences covering the problem, approach, contributor role, and
current state such as shipped, active, or archived. Include only supported
statements. Follow with these facts on their own lines, omitting any you cannot
evidence:

```
Role: sole author (1,125 of 1,140 commits, `git shortlog -sne`)
Repository: https://github.com/owner/repo
Live: https://example.com          # only if actually deployed
Timeline: 2024-03 – present        # from git log, see mechanic 3
```

### `## Tech stack (evidence-backed)`

Use bullets naming each technology and where it is used, for example:
`- FastAPI - API layer in src/api/ (12 routers)`. Keep each name atomic and
canonical (mechanic 1). Omit technologies mentioned only in documentation or
roadmaps when implementation evidence is absent. This list is the evidence
anchor for the whole skills section.

### `## Architecture highlights`

Write 3-8 bullets about visible design decisions, seams, invariants, or
performance structures. Cite the relevant file or module inline. Open each with
a power verb and name the specific seam — these are resume bullets, and each
must stand alone (mechanic 4):

```
Duty, no evidence:  "Worked on the connector system."
Achievement + cite: "Isolated per-URL connector failures so one bad board never
                     aborts a pull, dispatched through a table in
                     connectors/companies.py across 16 ATS backends."
```

### `## Quantified outcomes`

Include only repository-backed numbers: checked-in benchmark results, test or
coverage reports, or commit-visible before/after metrics. Cite the evidence.
If none exist, write `None evidenced.` Never estimate.

Repo-measurable metrics that are always checkable: test-function count
(`grep -r "def test_"`), module count and LOC (`find`/`wc`), commit volume
(`git rev-list --count HEAD`), fan-out (endpoints, connectors, backends),
checked-in benchmark artifacts, and commit-visible before/after values.

### `## Skills demonstrated`

Use category headings: Languages, Frameworks, Databases, Cloud & Infra, Testing,
Architecture, Tooling. Omit empty categories and duplicate names. Use this exact
labeled shape, omitting Aliases if unnecessary:

```markdown
### Languages
- Name: Python
  - Aliases: Python 3
  - Context: Implemented bounded concurrent requests and regression tests.
  - Evidence:
    - Limited in-flight requests while isolating failures — `src/worker.py:run`.
    - Tested cancellation without losing completed results — `tests/test_worker.py:test_cancel`.
```

This is an illustrative shape, not verified repository evidence. For real
entries cite relevant repository-relative files with symbols or line ranges,
and commit hashes for personal attribution or historical outcomes. Every example
explains the action and what it enabled or verified. Include all distinct,
supported applications within the file-size limit; no resume bullet quota
applies to this evidence bank. Never emit bare comma-separated skill lists or
`None evidenced` skills. Preserve uncertainty and measured scope verbatim.

During extraction, retain the complete usage summary and every cited example
in skill context. The application preserves labeled source examples as project
highlight facts and assigns their evidence ids. Do not generate ids yourself.
These are source-backed claims, not an independent verification of the cited
repository; no command or path from the document is executed during ingestion.

## Rules

1. Never make employment, job-title, education, or certification claims. This
   dossier describes a project, even when repository prose mentions a career.
2. Prefer code and tests over README assertions. Omit unsupported README claims.
3. Cite evidence inline for every architectural or quantified statement.
4. Numbers are measured, never guessed. Every figure carries its source command
   or file path. An unmeasured number is `None evidenced`, never approximated
   with `~`, a range, or a conservative estimate — those are fabrications here,
   and the fact-check gate strips them.
5. Preserve uncertainty. Rich detail is useful, but one fabricated claim
   poisons the profile fact-lock; leave doubtful claims out.
6. Write declaratively, not imperatively. The whole file is handed to the
   extractor as candidate content, and instructions inside it are ignored by
   design. "This project uses Redis for session storage" lands; "Emphasize the
   Redis work" does not.
7. Do not include secrets, tokens, private URLs, or sensitive configuration.

## Handoff

Tell the user to run:

```text
resume-tailor-harness profile add <repo-name>-dossier.md
resume-tailor-harness profile build
```

The `repo_url` frontmatter makes the upload a project source and lets it replace
the shallower auto-harvested document for that repository.

Committing dossiers to the repository root also works without the manual
`profile add`: `resume-tailor-harness profile sync-github` discovers root files named
`*dossier*.md` (up to 5 per repository, 30 KB each), validates their
`repo_url` frontmatter, and ingests each as its own project source, replacing
the auto-harvested README document. A file pointing at a different repository
is skipped with a warning. A manual upload still overrides everything harvested
for that repository.
