# Evaluate agent quality

This guide explains which evaluation to run and how to interpret its results.
Design rationale is in [the Phase 0 spec](../docs/superpowers/specs/2026-06-29-agent-quality-eval-harness-design.md),
recorded measurements are in [RESULTS.md](RESULTS.md), and judge calibration is
in [CALIBRATION.md](CALIBRATION.md).

## Choose an evaluation

| Question | Run |
| --- | --- |
| Did I break the eval harness itself? | `pytest tests/eval` (free, offline, in CI) |
| Did a prompt/config change move resume quality? | `make eval` |
| Did a change move cover-letter quality? | `python -m evals.run_cl_eval` |
| Does Scout still resolve companies to the right ATS board? | `python evals/run_scout_source_eval.py` |
| How does tailoring perform on user data? | `python scripts/tailor_health.py <workspace-db>` |

The first is free. The rest cost real API calls, and the Scout one makes live
network requests to third-party career sites.

## Test tiers

The live tier is outside `tests/`, because `make test-py` collects only
`tests/` and must not make paid calls. The offline tier is under `tests/`, so it
runs in CI. `tests/eval/` uses fake agents and tests the harness logic: the trap
checker must flag a forbidden term, `correlation` / `convergence` /
`trap_recall` must compute correctly on scripted inputs, and malformed cases
must be rejected. Passing `tests/eval` does not measure agent quality.

## Prerequisites for the live tier

1. An API key in `.env` for whichever provider your tiers name
   (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`).
2. `CHEAP_MODEL` / `MID_MODEL` / `PREMIUM_MODEL` set, or accept the defaults in
   `config.py` (`claude-haiku-4-5` / `claude-sonnet-5` / `claude-opus-5`).
3. A review config. `config/review.yaml` is gitignored, so `run_eval` falls back
   to `config/review.yaml.example` automatically when it is absent.

Budget expectation: 14 resume cases. Each runs tailoring, up to two panel and
reviser rounds, a judge, and one fact-check probe. Use `--limit` while iterating.

## Resume quality

```bash
make eval
```

Use this form when you intend to record a result:

```bash
uv run python -m evals.run_eval --config config/review.yaml.example --model deepseek:deepseek-v4-pro --out evals/reports/20260827T000000Z-baseline.md
```

| Flag | Effect |
| --- | --- |
| `--cases` / `--profiles` | Case and profile directories (default `evals/cases`, `evals/profiles`) |
| `--config` | Review config; falls back to `<name>.example` if the file is absent |
| `--model` | Pin every agent to one model ID; see the important behavior below |
| `--limit N` | First N cases only |
| `--out` | Markdown path; the JSON artifact is written alongside with a `.json` suffix |
| `--live-criteria` | Always call the extract agent instead of using each case's embedded `criteria` |
| `--fail-fast` | Stop at the first case that raises |

Both artifacts are rewritten in a `finally` block after every case. A crash or
interrupt after twelve cases still leaves a valid partial report on disk. The
command exits with code 1 if any case raises, and the report lists the failures.

Each of the 14 resume cases in [cases/](cases) contains a
`missing_skill`, `adjacent_skill`, `inflatable_metric`, or
`seniority_inflation` trap with hand-authored `forbidden_terms`. These terms are
case assertions, not a universal truth detector. When adding a case, exclude a
term whose mere mention could be truthful.

## Cover letters

```bash
uv run python -m evals.run_cl_eval --limit 4
```

This evaluation measures quality and does not block a run. It reads the same
`evals/cases` directory, keeps `target: cover_letter` cases (4 today), and
reports `finalQuality`, `trapOk`, `provenanceOk`, `reviseRounds`, and usage per
case. The reference point is the 77.5 mean recorded in [RESULTS.md](RESULTS.md).

## Scout ATS source resolution

```bash
uv run python evals/run_scout_source_eval.py
```

This evaluation does not use an LLM judge. It compares resolved board URLs with
[scout_source_cases.json](scout_source_cases.json), a manifest of manually
researched expectations stamped with `evidence_checked_at`. It writes
`.artifacts/scout-source-eval.json` and exits 1 if any case fails. A resolution
that exceeds `--timeout-seconds` (default 45) is a failure. Re-verify an
expectation by hand when a case starts failing, because the company may have
migrated ATS.

## Production health

```bash
uv run python scripts/tailor_health.py data/users/<id>/resume_tailor_harness.db
```

This command opens the database read-only and reports score distribution,
unscored rounds, the gate that blocked each failing round, and the mix of
blocking issues. It diagnosed the 2026-07-27 scoring bug and is the only
evaluation here that uses real jobs. Use it to check whether the synthetic
corpus reflects product behavior.

## Read the resume report

Per-case table columns:

| Column | Meaning |
| --- | --- |
| `quality` | Judge's `output_quality`, 0-100 |
| `trap_ok` | No forbidden term from any of the case's traps appears |
| `prov_ok` | Every bullet traces to a real fact id (`check_provenance`) |
| `cite_ok` | Every `must_cite` fact id appears in the output |
| `budget_ok` | Honors hard `max_experiences` / `max_bullets_per_role` |
| `bullets/target` | Actual versus `target_total_bullets`; this is a target, not a cap |
| `surfaced_round` | Which round the product read-side selector would show |
| `needs_attention` | No round passed the gate cleanly |
| `regressed` | A later round scored worse than an earlier one |
| `portfolio` / `mandatory` / `forbidden` | Evidence-portfolio arm only |

## Key aggregates

- `Mean output_quality` is comparable only with another run using the same judge
  model and `judge prompt sha256`. Both are printed under *Run metadata*.
- `Fact-check probe recall` runs the fact-check reviewer against a synthetic
  probe resume with exactly one planted unsupported claim. An unrelated
  complaint does not earn credit. The report shows `insufficient data` until it
  has five completed probes.
- `Reviewer panel_agreement` is the Pearson correlation between each advisory
  reviewer's score and the judge's quality for the same surfaced draft. It
  requires n>=5; otherwise, the report shows `insufficient data`. A reviewer
  whose score does not track quality is miscalibrated.
- `Weakest reviewer` ranks advisory reviewers, with agreement mapped from
  `[-1,1]` to `[0,1]`, against the fact-check gate's recall on a shared axis. A
  broken gate is therefore not hidden by a mildly anti-correlated reviewer.

The judge is profile- and trap-blind. It sees only the final resume, the job
description, and the rubric. It evaluates quality, while fact-lock is handled
by deterministic checks and the in-loop fact-check reviewer. Giving it the
profile would leak ground truth into `panel_agreement`.

## Calibrate the judge before citing absolute scores

Calibration is incomplete. [CALIBRATION.md](CALIBRATION.md) records a Claude
stand-in that had already seen the judge's scores, so it does not satisfy the
procedure. Both judge prompts changed on 2026-07-11 when band anchors and craft
standards were added. Those rows use an obsolete prompt hash. Until a human
anchor exists, claim only relative arm-to-arm deltas.

To calibrate the judge:

1. Run the live tier once and keep the timestamped JSON artifact.
2. Pick ~5 cases spanning the range. For each, read only the final resume, the
   job description, and the rubric. Do not read profile facts, trap labels,
   panel scores, or the judge's own score.
3. Rate `output_quality` 0-100 yourself, against the judge's own bands:
   90-100 ship-ready, 75-89 solid with minor gaps, 60-74 material gaps, below 60
   disqualifying for this job.
4. Record the rows in CALIBRATION.md with date, judge model, prompt sha256, your
   score, the judge's score, and the absolute error.
5. Use the judge only if MAE is below 10 and no single absolute error exceeds 20.

Re-run the calibration whenever `judge_prompt_hash()` or the judge model
changes. This step remains manual because an unvalidated judge cannot support
absolute claims.

## Run an A/B comparison

Change one variable. Pin the model, keep both artifacts, and record the result
in RESULTS.md with the config hash printed by the report.

```bash
uv run python -m evals.run_eval --config config/review.yaml.example --model <model> --out evals/reports/<stamp>-baseline.md
```

> The portfolio A/B described in RESULTS.md is confounded. Fix it before
> running. `config/review.match_plan.yaml` differs from
> `config/review.yaml.example` in several settings beyond the portfolio flag:
>
> | knob | review.yaml.example | review.match_plan.yaml |
> | --- | --- | --- |
> | `evidence_portfolio_enabled` | false | true |
> | `max_rounds` | 2 | 3 |
> | `merged_advisory` | true | false (default) |
> | `early_stop_on_regression` | true | false (default) |
> | `score_bands` | true on all four advisory reviewers | absent |
> | `style_guide_path` | `config/style_guide.md` | inherits the default |
>
> Passing the same `--model` to both arms neutralizes `tailor_tier`,
> `reviser_tier`, and per-reviewer tier differences. It does not neutralize the
> settings above. A quality delta between these files cannot be attributed to
> the portfolio planner. Create a clean arm by copying `review.yaml.example`,
> setting `evidence_portfolio_enabled: true`, and changing nothing else.

The portfolio activation gates are listed at the end of
[RESULTS.md](RESULTS.md). They require a >=5 point relevance gain, >=90%
mandatory-evidence recall, zero forbidden claims, no provenance, fact-lock, or
trap-recall regression, >=7 wins in a blind comparison of ten real jobs, and
acceptable latency and cost.

## Important behavior

- With `--model`, the evaluation uses a different pipeline topology.
  `build_eval_bundle` constructs every advisory reviewer individually and does
  not build the merged advisory agent. As a result, `merged_advisory: true` in
  the config is ignored. `make eval` without `--model` goes through
  `build_tailor_bundle` and honors that setting. Do not compare a `--model` run
  with a bare `make eval` run.
- In merged advisory mode, `panel_agreement` is less independent. The four
  advisory scores come from one call to one model and then fan out into
  per-reviewer critiques. The metric measures one agent's per-dimension
  calibration, not four independent raters.
- Small-sample metrics abstain. `correlation` needs n>=5, and probe recall needs
  five completed probes. Both print `insufficient data` until then. A
  `--limit 3` run has no meta-evaluation signal.
- Provider cost can be `unknown`. The metering decorator reports the provider's
  value and does not estimate a dollar amount from call count.
- A round that fails provenance has no comparable aggregate score. The runtime
  records its placeholder as `None`, rather than a quality regression. A
  fabricated `0` caused the 2026-07-27 bug.

## Coverage gaps

The harness evaluates the tailor, reviser, reviewer panel, evidence-portfolio
planner, judge, cover-letter writer, and Scout source resolution. Roughly thirty
other `build_*_agent` functions have fake unit tests but no quality measurement,
including:

profile coach · mock interviewer · synthesis and entailment · project extractor ·
taxonomy group classifier · incremental canonicalizer and themer · aspect
classifier · discovery fit and relevance · URL extractor · email writer ·
Career Lab persona and router · bullet dedup.

To evaluate one of these areas, add a hermetic case corpus with hand-authored
expectations. Start with deterministic checks because they are reproducible and
free. Use an LLM judge only for behavior that cannot be checked mechanically,
and calibrate that judge before citing its absolute scores.

## Adding a resume case

Drop a JSON file in [cases/](cases) matching `EvalCase` in
[schema.py](schema.py): `id`, `profile_ref` (a file in [profiles/](profiles)),
`jd_text`, an optional pre-extracted `criteria`, a non-empty `rubric`, and any
`traps`. Each trap needs a `probe_claim` and a `probe_provenance` pointing to a
real experience-bullet ID in the referenced profile. The harness builds the
recall probe from it and raises if the ID does not resolve. `tests/eval` rejects
malformed cases before any paid evaluation runs.
