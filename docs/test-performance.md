# Test runtime

The offline suites must keep the same tests, assertions, production password
hashing, database migrations, real PDF compilation, and performance regression
checks. Speed comes from scheduling independent work, not excluding slow tests.

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
tests merely to save setup time.

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

For diagnosis, a profile of `tests/api/test_auth_email_flows.py` attributed
5.33 seconds to PBKDF2 in a 9.54-second test run (seven tests). Those production
hashing checks remain intact. The health API sample took only 1.27 seconds for
five tests, showing why distributing work by cost matters more than dividing
it into equally sized static groups.

References: [pytest durations](https://docs.pytest.org/en/stable/how-to/usage.html#profiling-test-execution-duration),
[pytest-xdist scheduling](https://pytest-xdist.readthedocs.io/en/stable/distribution.html),
and [Vitest performance](https://vitest.dev/guide/improving-performance.html).
