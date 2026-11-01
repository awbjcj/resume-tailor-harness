# Project dossier evidence in the personal profile

Project documents using the `project-resume-dossier` skill's labeled format now
produce a reusable evidence bank. Profile construction preserves source detail;
the later tailoring step chooses the examples relevant to a job and page budget.
For the labeled format, the model extracts project metadata from the summary
and technology sections; the application copies the complete evidence sections
directly. This avoids asking the model to reproduce a large evidence bank within
its output-token limit.

For each project, the build retains:

- Every architecture highlight and quantified outcome as a project highlight fact.
- Each skill's canonical name, separate aliases, full usage context, and all
  explained evidence examples, including repository paths, symbols, commits,
  measurement scope, and qualifications.
- A separate, stable fact ID for each distinct example, linked from the skill's
  `evidence_fact_ids`. Identical examples shared by multiple skills use one fact.
- Source document references on facts and all contributing source references
  and project contexts when the same personal skill appears in several projects.

The source sections use `# Project:`, `## Tech stack (evidence-backed)`,
`## Architecture highlights`, `## Quantified outcomes`, and
`## Skills demonstrated`, with category subheadings and labeled entries:

```markdown
### Languages
- Name: Python
  - Aliases: Python 3
  - Context: Implemented bounded requests and cancellation regression tests.
  - Evidence:
    - Limited in-flight requests while isolating failures — `src/worker.py:run`.
    - Tested cancellation while preserving completed results — `tests/test_worker.py:test_cancel`.
```

This snippet illustrates the structure, not facts about a real repository.
A usage context and at least one explained repository citation are required.
Bare paths and uncited examples are omitted with build diagnostics. Fenced
examples are ignored. Older dossiers and harvested README documents continue
through the general project extractor, whose instructions also require complete
usage context and citations without a resume-sized bullet quota.

The existing project schema still prevents employment, education, and
certification sections from being created by project extraction. Repository
identity and timeline remain project fields. Distinct monorepo deliverables
retain their body `Repository:` deep links rather than sharing one project key.

Stable evidence links survive fragment caching and project deduplication. Skill
matching uses those links and project highlights, so broader skills such as API
design or concurrency can identify their project even without appearing in its
technology list. Tailoring's supporting-facts resolver supplies the cited usage
examples to the fact-check reviewer. Provenance and numeric gates still apply
to individually cited facts.

The extractor cache version changed, so the next full profile build refreshes
project fragments automatically. A skills-only rebuild uses saved facts and
does not reread source documents; run a full profile build to ingest richer
dossier evidence first. No personal profile is rewritten merely by updating
the application code.

Evidence retention verifies the supplied source structure, not the truth of a
remote repository or personal authorship. The dossier author must still establish
contribution scope and measured outcomes from code, tests, and history. Ingestion
does not fetch cited files or execute commands printed in documents.
