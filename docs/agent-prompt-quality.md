# Agent prompt quality refresh

This change adds `career-quality-v1` task guidance to all 54 editable production
prompt keys. The 55th key, `reviewer-fact-check`, was audited and deliberately
left unchanged, along with the independent evaluation judges. Holding those
truth/quality checks fixed makes before/after comparisons interpretable.

## Research inputs

Public GitHub sources were inspected on October 8, 2026 (America/New_York).
The repositories were selected for relevant implementation and substantial
adoption, not as evidence that their prompts outperform this application.
Stars are a point-in-time popularity indicator, not a quality benchmark.

| Project | Stars observed | Source inspected | Adaptation |
| --- | ---: | --- | --- |
| Resume Matcher | 28,602 | [Prompt templates](https://github.com/srbhr/Resume-Matcher/blob/63fc344a9a59a79db6fa9d96aff188dc9faf545b/apps/backend/app/prompts/templates.py), [bullet scoring](https://github.com/srbhr/Resume-Matcher/blob/63fc344a9a59a79db6fa9d96aff188dc9faf545b/apps/backend/app/services/bullet_scoring.py) | Select evidence by actual job requirements; distinguish selection from rewriting; preserve identities and dates; prefer targeted edits with traceable source content. |
| Career Ops | 73,835 | [Interview practice protocol](https://github.com/career-ops-hq/career-ops/blob/4164109d85218b27719081c5cc8b7254886b90af/modes/interview/practice.md) | Ask one question, follow the actual answer, ground feedback in what was said, probe reflection, and distinguish observable text structure from unmeasured spoken delivery. |
| AI Job Search | 45,313 | [Job evaluation framework](https://github.com/MadsLorentzen/ai-job-search/blob/a011214d60f943770e33f7d5f070e1a5f91e3822/.claude/skills/job-application-assistant/04-job-evaluation.md) | Use anchored score bands, match the function of work rather than titles, and distinguish skill/experience evidence from logistical constraints and unknown eligibility. |

The local **ATS Resume Checker**, **Academic CV Builder**, **Cover Letter Writer**,
and **Career Changer Translator** skills were also read. Their useful principles
are task-specific evidence selection, clear contribution/action/result writing,
distinct cover-letter examples, role-sensitive research emphasis, and honest
transferability. No external prompt or skill was installed or executed. The
application's hash-verified runtime skill files and lock manifest are unchanged.

Several recommendations were deliberately rejected:

- Mandatory numbers in every bullet or answer, invented estimates, and example
  accomplishments that introduce facts not present in the original.
- Universal page, keyword-percentage, or ATS-pass rules. This application's
  length budget, schema, and deterministic skill tiers remain authoritative.
- Treating a company-wide sponsorship statement or historical filing as proof
  of role-level eligibility; deriving legal conclusions from silence.
- Importing external score weights or gates. Existing fit bands, review weights,
  pass thresholds, and runtime decisions are unchanged.
- Showing interview coaching inside the spoken question. This product keeps
  hints in metadata and feedback in the debrief.

## Composition and coverage

`prompts/quality.py` is a dependency-free, explicit policy map.
`with_guidance()` composes the builder's existing invariant instructions,
versioned application quality guidance, then subordinate user guidance.
`prompts/registry.py` uses the same quality composition so the settings catalog
shows the application rules that the agents actually receive. Dynamic context,
house style, selected skills, and persona settings still come from their builders.
Where a builder supplies run provenance, `AgentRunner` appends the quality
policy version to that run's policy id without mutating the caller's metadata.
Literal, synthesis, and project extraction cache versions are advanced so an
explicit profile rebuild does not silently reuse fragments from the old prompts.

The registry now also includes eleven previously omitted keys: Career Lab's
three agents, evidence portfolio planning, both H-1B agents, both hiring-contact
agents, role preparation, taxonomy escalation, and taxonomy maintenance.
Career Lab is grouped with Profile in the existing settings categories.
Scraper page understanding shares `scraper-learn`; scraper posting extraction
shares `url-ingest`. Both variants receive appropriate shared quality guidance
while retaining their own schemas and base instructions. Speech synthesis is
an audio endpoint rather than a career reasoning agent and is unchanged.

| Agent group | Quality focus |
| --- | --- |
| Resume authors, editors, planners | Direct evidence before title/metric appeal; distinct coverage; contribution versus ownership; research status; narrow revisions. |
| Advisory reviewers | Passage-specific deductions and feasible repairs; separate qualification gaps from presentation gaps; independent dimensions and no ATS/hiring probability claims. |
| Cover letters and email | Complementary examples, supported recipient/company context, one clear next step, no invented relationships or commitments. |
| Discovery, fit, extraction, scraper, Scout | Required versus preferred criteria, one posting's identity, unknown versus mismatch, observed controls, bounded source verification. |
| Profile extraction, synthesis, verification, inference, dedup | Source precision, clause-level support, implementation versus roadmap, ownership, conservative inference and deduplication. |
| Taxonomy and aspect classification | Exact token/id coverage, synonymy versus relatedness, stable and pinned identities, classification without rewriting facts. |
| Coaching, interviews, preparation | One useful question, qualitative evidence, question-specific grading, answer-specific practice steps, no inferred speaking measurements. |
| Company/contact/sponsorship research and formatters | Entity, date, and source precision; historical versus current claims; uncertainty survives formatting. |
| Career Lab routing, drafting, metadata | Outcome-based routing, conversation corrections, one verified skill, draft/verified/future-action distinctions. |

The merged advisory builder embeds each individual reviewer's new rubric.
Updating only the standalone reviewers would leave the default production
review path behind. Custom reviewer names receive generic evidence-based review
guidance without inheriting another reviewer's specialization.

Conflicts in the original base prompts were fixed directly: interview debriefs
now use question-appropriate 1–5 anchors instead of requiring STAR plus a number
for every answer; typed transcripts do not establish spoken timing; coaching
can finish with qualitative evidence; writing preserves contribution verbs;
and summary guidance names `summary_provenance` as its evidence source.

## Validation and measurement

`tests/test_prompt_quality.py` scans production builders to catch an agent
missing from the policy map/catalog, checks real builder/catalog parity,
preserves the immutable gate, checks merged/standalone rubric parity, and
bounds added context to fewer than 2,400 characters per key. These are
composition and regression checks, not evidence of improved model behavior.

Two synthetic resume cases extend the existing executable evaluation corpus:

- `case_15_qualitative_contribution`: preserve supervised contribution and
  useful qualitative evidence without inventing a metric or leadership.
- `case_16_research_status`: present a submitted methods contribution without
  promoting it to publication, first authorship, or investigator status.

The cases include source-backed `must_cite` ids and planted unsupported claims
for the existing trap/provenance checks. They can run through `evals.run_eval`
without a new judge or schema. Keep the same cases, model, configuration, skill
manifest, style, and judge hash in both comparison arms. The repository's
existing judge remains uncalibrated for absolute scores; small live samples
support only tentative relative observations, never a claim about hiring rates.

For a full comparison, use `evals/README.md`. A pinned `--model` run constructs
individual reviewers; it does not test the default merged-panel topology.
Interview, coaching, research, taxonomy, and Career Lab still need separate
live quality evaluations. Unit tests must not be presented as those measurements.

## October 8 live comparison: incomplete, no demonstrated gain

The baseline loaded the original source at
`53661cf742d485309c3abafca2f0a7b53b329ea4` from a temporary snapshot. Both arms
used `deepseek:deepseek-v4-pro`, identical runtime skill hashes, an empty house
style, and the same configuration: one review round, no provenance retries,
individual advisory reviewers, and portfolio planning disabled. Effective
writer/reviewer prompt fingerprints were saved; the judge and fact-check
fingerprints were verified identical across arms.

The intended five cases were missing skill, adjacent skill, metric-rich evidence,
qualitative contribution, and research status. The baseline completed four,
then was stopped during research status after more than six minutes without
report progress. The candidate was limited to the same first four cases but
hit a 12-minute wall-clock limit during the metric-rich case. Both arms emitted
JSON parsing warnings. Only the two completed, matched cases are compared:

| Case | Baseline judge score | Candidate judge score | Difference |
| --- | ---: | ---: | ---: |
| Missing skill | 55 | 42 | -13 |
| Adjacent skill | 62 | 58 | -4 |
| Matched mean | 58.5 | 50.0 | -8.5 |

Both arms passed the forbidden-term traps, provenance, required citations,
and budget checks on these two cases. The unpaired baseline scores of 88
(metric-rich) and 82 (qualitative contribution) are not included in the paired
mean. This small, incomplete, stochastic comparison does **not** demonstrate
an improvement; the observed matched quality scores decreased. It cannot
establish a general regression or improvement across agents, either. There is
no valid human judge calibration, and these two cases intentionally lack core
job qualifications. No latency or cost improvement is claimed; provider costs
were unknown.

The prompt refresh remains a reviewable implementation of clearer contracts,
not a measured performance win. A balanced, completed comparison with repeated
runs and blind human review is still needed before claiming better output
quality. Do not tune the acceptance threshold to erase these results.

Generated reports, original model outputs, config, logs, and prompt fingerprints
are saved locally in [evals/reports/20261008-prompt-quality/](../evals/reports/20261008-prompt-quality/),
including [comparison.json](../evals/reports/20261008-prompt-quality/comparison.json).
That directory is gitignored under the repository's existing report policy;
the table above records the results in versionable documentation. Temporary
source copies were moved out of the checkout into the operating system's temp
directory, and no evaluation process was left running.

Offline validation: the full suite passed with 4,172 tests and five skips.
Subsequent focused checks passed after the final provenance/cache changes,
including all 177 runner/provenance/cache boundary tests. Ruff and diff
whitespace checks passed. None of these offline results measures LLM quality.
