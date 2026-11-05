# Verification

The kit contains reproducible static checks and an optional Chromium verifier.
Observed results for this snapshot are recorded in `../evidence/browser-report.json`.
Representative desktop and mobile captures are stored beside the report.

## Observed results — 2026-11-04

| Check | Result |
| --- | --- |
| Static artifact check | 316 base tokens; three themes; 30 text/control contrast pairs; 78 source colors retained exactly |
| Responsive layouts | 33 checks passed, including 12 at 200% root text and one forced-colors layout |
| Automated accessibility | Eight axe runs; zero reported violations; incomplete rules retained for review |
| Browser interactions | Ten grouped interaction/environment checks passed; no page errors or external requests |
| Optional adapters | Strict React TypeScript, rendered field/disabled semantics, and Tailwind v4 compilation passed |
| Visual inspection | Light/dark desktop overviews, full-page exports, and Chinese mobile preview inspected |

The browser report also records measured contrast for the rendered tone badges.
The exported preview was checked in Chromium; no cross-browser or production
application verification is implied.

## Mechanical design findings reviewed

Two file-scoped detector exceptions were recorded in the source repository:

- `overused-font` / `Geist` in `styles/fonts.css`: intentional preservation of
  the originating project's typeface, consistent with this extraction brief.
- `flat-type-hierarchy` in `preview.html`: a false positive from scanning markup
  without resolving the external token-driven CSS. Computed body size is 15px;
  section headings are 24px on mobile and 30px on desktop; the title is
  43.2–72px. Both heading/body ratios exceed the detector's 1.25 threshold.

[Measured evidence](../evidence/design-review.json) records the 320px, 390px,
and 1440px checks. These exceptions leave other rules and files active. No visual
change was needed, and no finding was left unresolved in this review.

## Reproduce

From this artifact directory, using Node 22 or newer:

```sh
npm run build
npm run check
```

Static checks have no npm dependencies. The optional browser verifier needs a
host installation of `@playwright/test`, `axe-core`, and the Chromium browser
used by Playwright. It does not install packages or download browsers itself.
Use the host's tooling or provision those separately.

When running from the original repository root:

```sh
node artifacts/teal-ink/scripts/verify-browser.mjs --modules-from web/package.json
node artifacts/teal-ink/scripts/check-integrations.mjs --modules-from web/package.json
```

In a destination project, use its package path instead:

```sh
node vendor/teal-ink/scripts/verify-browser.mjs --modules-from package.json
node vendor/teal-ink/scripts/check-integrations.mjs --modules-from package.json
```

Without `--modules-from`, dependencies resolve from this artifact's package.
Use `--evidence path/to/results` to place browser results somewhere else.
The verifier creates an ephemeral loopback server, then closes it and the
browser when done. It also checks that `preview.html` works through `file://`.

## Coverage

- Token references, cycles, types, layer boundaries, unique CSS names, generated
  output freshness, and artifact-local links.
- Exact source light/dark hex colors and numerical contrast for the main text,
  action, accent, control-boundary, and focus pairs across all three themes.
- Light/dark × English/Simplified Chinese × 320/390/768/1024/1440px layouts.
- 200% root text at 320/768/1440px for both languages and both workspace themes.
- axe accessibility checks at 320px and 1440px for both languages/themes.
- Nested theme component resolution, source canvas colors, gateway mint,
  system preference changes, and persisted preview choice.
- Native dialog focus containment, Escape cancellation, focus return, repeated
  open/confirm/cancel behavior, and a keyboard skip link.
- Form errors and focus, loading state, token search/copy/empty states, direct
  offline file use, coarse-pointer targets, reduced motion, and forced colors.

The verifier uses Playwright's [browser emulation APIs](https://playwright.dev/docs/emulation)
and injects the installed axe script. `incomplete` rules in the report still need
human assessment. Automated checks do not establish complete WCAG conformance,
screen-reader usability, cross-browser parity, or the behavior of a destination
application. Screenshots establish the exported preview's appearance only.

The integration verifier resolves TypeScript, React, React DOM, React types,
and Tailwind from the indicated host package. It records versions and results
in `../evidence/integration-report.json` without changing host files.

The optional React adapter is type-checked against the source project's React
19/TypeScript installation during extraction. This does not establish every
destination bundler or framework integration. The Tailwind adapter is checked
with the source project's installed v4 compiler, separate from browser CSS.
