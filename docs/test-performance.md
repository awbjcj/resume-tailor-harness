# Test runtime

The offline suites preserve behavior coverage, production password hashing,
database migrations, real PDF compilation, and performance regression checks.
Reduce runtime by scheduling independent work and consolidating related cases
that can safely reuse initialization within one test.

## Python

Install the locked development dependencies with `uv sync --frozen`. The normal
`uv run pytest` command uses pytest-xdist with at most four worker processes and
work-stealing scheduling. Smaller machines use their available CPU count. Idle
workers take queued tests from busy workers so expensive API or rendering tests
do not leave the rest of the machine idle.

Each worker has its own Python module state and pytest temporary directory.
Function-scoped fixtures still run for every test. Keep writable files under
`tmp_path` and databases private to the test; do not introduce fixed output
paths or shared ports. Do not share a mutable application or database across
tests merely to save setup time. Within one test, use pytest 9's `subtests`
fixture for compatible input matrices: each case gets its own failure report
without rerunning the application's fixtures. Rejected inputs must leave the
shared state unchanged; restore mutable fake inputs before each case. Keep
cases with incompatible startup settings or destructive side effects separate.

```sh
uv run pytest                                     # complete suite
uv run pytest -n 0 tests/api/test_app_health.py     # cheap focused run / debugging
uv run pytest -n 0 --durations=40                  # serial timing baseline
uv run pytest --durations=40 --junitxml=output/pytest.xml
```

The ten slowest setup/call/teardown phases are reported by default, including
in CI. `-n 0` avoids the repeated import/collection cost of worker startup for
small selections and makes profiles easier to interpret. Override the cap
explicitly with `--maxprocesses` only after measuring memory and contention.

Measured on Windows with Python 3.13.2 and a Ryzen 9 5900HX on 2026-10-30:

| Configuration | Pytest runtime | Result |
| --- | ---: | --- |
| Original serial suite | 836.79 s | 4,698 passed / 5 skipped |
| Four workers, work-stealing | 294.21 s | 4,698 passed / 5 skipped |

That is a 64.8% reduction (13m 57s to 4m 54s). The JUnit reports have identical
test identities and statuses, including the five existing skips. The parallel
command took 298.75 seconds including process startup and shutdown.

The baseline API group accounted for 412.57 seconds of test/fixture time. The
largest individual test, Gmail's 5,000-application / 10,000-message resumable
sync regression, took 173.78 seconds serially and 181.32 seconds under parallel
load. Its full dataset and assertions remain intact; it is still the main
single-test limit on further scheduling gains.

## Web

`npm run test:run` (from `web/`) uses up to four `vmThreads` workers. Every file
still gets its own module state, VM context, and jsdom window; `isolate` remains
enabled. Workers reuse the expensive environment imports and are recycled at a
512 MB memory threshold. The existing 15-second test timeout and all test
selection patterns remain unchanged.

`src/test/web-streams.ts` exposes Node's real Web Streams implementations only
where the VM global lacks them, before MSW loads. Request interception, strict
unhandled-request errors, handler cleanup, and language reset still run for
each isolated test file. This keeps streaming tests on real stream primitives.

For debugging VM-specific behavior, use the original process pool:

```sh
cd web
node node_modules/vitest/vitest.mjs run --pool=forks
```

On Windows (Ryzen 9 5900HX, 16 logical CPUs, Node 24.15.0), the complete suite
produced these Vitest-reported times on 2026-10-30:

| Configuration | Runtime | Result |
| --- | ---: | --- |
| Original process pool, 15 workers | 186.39 s | 215 files / 965 tests passed |
| Process pool, 4 workers | 208.42 s | 215 files / 965 tests passed |
| Isolated VM pool, 4 workers, 512 MB recycling | 79.10 s | 215 files / 965 tests passed |

The selected configuration is 57.6% faster than the original. Reducing worker
count alone was slower, so it was not retained as the optimization. jsdom
environment creation fell from 38% to 7% of tracked time. The two runs with
JSON reports (four-process and VM) have identical test identities and statuses;
the original run has the same file and test counts.

Validation also passed Ruff, ESLint on the changed web test configuration and
setup, and `tsc -b`. No production application code or test assertions changed.
Raw local reports are under the ignored `output/test-performance/` directory:
`pytest-before.xml`, `pytest-after.xml`, `vitest-before.log`,
`vitest-four-workers.json`, `vitest-after.json`, and `comparison.json`.

## Measurement method

Run the complete Python and web suites separately on the same checkout and
machine, using the same report options before and after. Preserve JUnit/JSON
reports and compare test identities, statuses, and counts as well as elapsed
time. Worker durations are overlapping wall-clock phases, so adding them does
not give the duration of a parallel run. Local timings vary with other work
on the machine; they are observations, not CI time limits.

## Shared-initialization consolidation (2026-11-01)

Related API and UI checks now follow one lifecycle where possible: defaults,
validation, save, read-back, and cleanup reuse the same client or component.
Validation matrices use named subtests, preserving every original input and
continuing after individual failures. Fake billing prices are restored before
each case so one invalid field cannot mask another. Applications, databases,
and writable fixtures remain isolated between collected tests.

The seven OpenAPI generations formerly spread across five modules are now one
contract check with six named sections. It also checks that `/openapi.json`
serves the generated schema. Release-policy checks that do not use Git no
longer initialize repositories; compatible preview, publish, and validation
checks share their local repository pair.

Four redundant tests were removed: the duplicate public-health status check,
the identical Ashby HTML fallback, the secondary-location assertion already
present in Ashby's field mapping, and the two-stage ordering check covered by
the larger pipeline priority test. The keyword-removal check now requires an
empty output instead of checking for an empty substring.

| Measurement | Before | After |
| --- | ---: | ---: |
| App builds in the profiled 13-file Python selection | 209 | 124 |
| Git repository pairs initialized by release tests | 16 | 11 |
| OpenAPI schema generations across the suite | 7 | 1 |
| Collected cases in the 18 changed Python files | 263 | 166 |
| Additional named pytest subtests | 0 | 80 |
| Collected cases in the 8 changed web files | 45 | 25 |
| Matched web selection, mean elapsed time | 19.30 s | 14.66 s |

The profiled selection builds 40.7% fewer apps. The matched web selection is
24.0% faster. Its original and revised tests ran against unchanged production
components in before/after/after/before order: 20.56/14.03/15.30/18.03 seconds.
All four runs passed. The temporary original test copies were removed afterward.

Complete validation passed 5,033 Python tests plus 109 subtests (six existing
skips), and 1,021 web tests in 225 files. All 4,873 untouched Python test
identities/statuses, all six skip identities, and all 996 untouched web
identities/statuses match the baseline. Ruff, Pyright, ESLint, and TypeScript
checks also passed.

These measurements establish less initialization and a faster affected web
selection, not a full-suite speedup. Complete pytest time was essentially
unchanged (206.29 to 206.05 seconds). Complete web elapsed time varied from
48.65 to 94.12 seconds, with unchanged tests also taking substantially longer
in the latter run. The profiled serial Python selection passed in 161.15 and
148.93 seconds; profiler overhead means those times should not be compared
with normal suite runs. Pytest subtest reports also include child timings, so
summing JUnit case durations can double-count work.

Raw reports, the fixed Python selection, input/identity audits, initializer
counts, and matched web timings are in the ignored `output/test-consolidation/`
directory. The performance budgets and production behavior were unchanged.

For diagnosis, a profile of `tests/api/test_auth_email_flows.py` attributed
5.33 seconds to PBKDF2 in a 9.54-second test run (seven tests). Those production
hashing checks remain intact. The health API sample took only 1.27 seconds for
five tests, showing why distributing work by cost matters more than dividing
it into equally sized static groups.

References: [pytest durations](https://docs.pytest.org/en/stable/how-to/usage.html#profiling-test-execution-duration),
[pytest-xdist scheduling](https://pytest-xdist.readthedocs.io/en/stable/distribution.html),
and [Vitest performance](https://vitest.dev/guide/improving-performance.html).
