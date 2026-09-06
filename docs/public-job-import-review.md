# Public URL import implementation review

Reviewed locally against the approved design and plan dated 2026-09-05, using
`47b9ca59` as the pre-implementation baseline and including working-tree additions.
The standards and specification reviews were conducted directly, without agents,
as requested. References: root/nested `CLAUDE.md`, the approved design, and
`docs/superpowers/plans/2026-09-05-non-ats-url-import.md`.

## Standards review

Fixed findings:

- Moved draft editing and source rollback behavior into the service layer;
  routers retain request adaptation and error mapping.
- Reused the existing provider runner, prompt guidance, spend governance,
  tenant sessions and canonical ingestion instead of creating another provider
  or job persistence path. Regenerated OpenAPI and both TypeScript copies.
- Extended reset/settings transfer explicitly for the new database records.
  Exported definitions exclude evidence and user job corrections; imported
  definitions require renewed review.
- Kept implementation isolated from the unrelated work in the main checkout.
  Formatting changes were confined to touched files.

Ruff, frontend lint, TypeScript, localization and production build checks pass.
No remaining blocking standards finding was identified in this review.

## Specification review

Fixed findings with regression coverage:

- Distinct inline postings could collide at one board URL. Stable source posting
  identities now participate in ingestion, without title-only identity matching.
- Canonical duplicates and progressed jobs needed observations retained without
  resetting progress or replacing frozen content.
- Salary validation could combine evidence across bands. Amounts, units and
  location associations must now be supported within each band's own source text.
- User-supplied corrections could alter identity or overwrite a newer override
  through an old draft. Identity fields are immutable and field revisions are
  checked at approval.
- Changed source values beneath existing corrections now retain a review conflict
  while preserving the correction, including explicit null values.
- Revalidation must preserve deliberate sample corrections while keeping blocked
  acquisition unapprovable. Browser disablement is enforced at child startup.
- Per-resource pacing unnecessarily delayed every script. Resources now share
  a leased page acquisition; host courtesy delays remain between acquisitions.
- Expired dynamic pages cannot trust HTML ETags alone. They render again; static
  pages can reuse validated conditional responses.
- Browser unavailability, robots/access blocks and exhausted throttling retries
  now have distinct terminal reasons instead of misleading empty/generic results.
- When sources deduplicate to one job, the correction editor now targets the
  source of the latest displayed observation.
- Saving a new draft revision remounted the editor before approval errors could
  display. The editor now retains revision state and displays the conflict.

Coverage includes nullable/multiple salary and location fields, evidence checks,
URL identity, shared leases, tenant persistence/CAS, limits, pagination repetition,
cache refresh, API/lifecycle behavior and editable UI approval. No remaining
blocking finding was identified for the implemented public-page workflow.

## Measured verification and boundaries

- Full backend suite: **3,677 passed, 5 skipped**. The latest correction-editor
  API regression was also verified with its focused route suite (**4 passed**).
- Full frontend suite: **193 files, 780 tests passed**.
- UI Chromium checks: **2 passed**, at 390px and 1280px; API responses are controlled
  fixtures. Screenshots were captured and the mobile preview inspected.
- Real Chromium fixtures: **8 passed**, covering dynamic/delayed content, private subresource
  rejection, cancellation, cleanup, and analyze/edit/approve/restart/re-pull.
- The Docker image built successfully. The nonroot capability probe passed with
  outbound networking disabled and the documented seccomp profile. Latest source
  was mounted read-only for the subsequent capability check. The host's default
  Docker seccomp policy did not support the sandbox; no sandbox bypass was added.
- The ordinary backend suite deliberately skips opt-in real-browser tests;
  those were also run separately.

These checks use controlled pages and deterministic/fake model responses. They do
not certify arbitrary live-site coverage or live-provider extraction accuracy.
The added Windows browser CI workflow has been checked in but has not run on
GitHub. No Railway/production deployment or production host isolation check was
performed. See [runtime instructions](public-job-import.md).
