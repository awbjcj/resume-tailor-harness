# Versions and releases

Application versions are Git tags in **vMAJOR.MINOR.PATCH** format. The latest
GitHub release appears in both README version badges. Package metadata and the
Python SDK keep their own package versions; an application milestone does not
publish a package or attest that a deployment completed.

## Automatic releases

`.github/workflows/release.yml` runs every Monday at 14:23 UTC. It runs from the
repository's default branch (`dev`) and reads the complete history of
`origin/main`. It never commits to a branch or releases unpublished `dev` work.
The latest full `ci-main.yml` **push** run for the exact target SHA must have
completed successfully, including Python, web build, and security audit jobs.
A running, failed, cancelled, missing, or unrelated CI run blocks publication.

Changes since the previous application tag determine the next version:

| Commit | Bump | Example from v0.5.0 |
| --- | --- | --- |
| `feat!:` / `fix(api)!:` or a `BREAKING CHANGE:` / `BREAKING-CHANGE:` footer | Major | v1.0.0 |
| `feat:` / `feat(scope):` | Minor | v0.6.0 |
| `fix:`, `perf:`, `revert:`, Git's `Revert "..."`, or `chore(deps...):` / `build(deps...):` | Patch | v0.5.1 |
| Only documentation, tests, CI, refactoring, or other maintenance | Wait for a release-worthy change | No release |

The highest bump wins; a manual bump cannot understate detected changes.
Mark breaking changes explicitly, and use Conventional
Commits for features and fixes. Unclassified messages do not trigger a release.
Release notes group the relevant commits and link to the complete comparison,
which also includes maintenance commits. No changes means no tag or release.
Automatic mode waits at least seven days after the last published release.
The workflow serializes publication and does not run on each commit or PR.

For an early release, open **Actions → Batched semantic releases → Run workflow**
on `dev`, choose an explicit bump, and enable **publish**. Explicit bumps bypass
the seven-day interval; the main CI requirement still applies. Leaving publish
unchecked previews the result. Changes to `dev` still need the normal promotion
PR into `main` before they can be released.

Local equivalents (Python 3.10+, git, and authenticated GitHub CLI):

```powershell
git fetch origin --tags
python scripts/release.py release
python scripts/release.py release --bump patch --publish
```

The workflow uses only `GITHUB_TOKEN` with contents write and Actions read
permissions. No personal access token, release PR into main, branch protection
exception, or package registry credential is needed.

## Historical labels

The curated `.github/release-history.json` covers all existing `main` history,
from the first June 8, 2026 scaffold to the October 29, 2026 promotion. Five
monthly tags identify snapshots, and just three consolidated GitHub releases
present that history:

| Tag | Snapshot | GitHub release coverage |
| --- | --- | --- |
| v0.1.0 | June 29 | Initial history through June |
| v0.2.0 | July 31 | Tag only; included in v0.3.0 notes |
| v0.3.0 | August 30 | July and August |
| v0.4.0 | September 30 | Tag only; included in v0.5.0 notes |
| v0.5.0 | October 29 | September and October; latest |

These are retrospective development milestones under major zero, not inferred
historical promises of API compatibility. Notes preserve the snapshot dates
and identify the releases as retrospective; publication timestamps are current.
Old snapshots predate today's CI gate and are explicitly historical. Future
releases always require current CI evidence.

The backfill command previews by default:

```powershell
python scripts/release.py backfill
python scripts/release.py backfill --publish
```

It validates every version, original commit date, and first-parent main target
before writing anything. Existing tags must match their original SHAs. Reruns
skip matching tags and releases, never move tags, and recover missing releases
after an interrupted backfill. Only the newest historical release is marked
latest. The backfill is a one-time operation, separate from the weekly workflow.
