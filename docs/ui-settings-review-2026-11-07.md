# UI layout and settings review — 2026-11-07

This pass reviews 40 route states, including both Profile tabs, all 12 settings
destinations, the authenticated workspaces, account/admin, setup, and authentication.
It preserves the existing Teal & Ink identity and concentrates changes on task
hierarchy, configuration editing, recovery, and responsive layout.

## Method and baseline

Method: dual-agent (A: `/root/design_review` · B: `/root/ui_evidence`). A reviewed
source without seeing detector output; B scanned 318 production markup files
after excluding tests from the 523-file source tree. Their isolated browser
inventories were empty. The coordinator supplied the rendered review in the
in-app browser and ran the production browser tests.

The baseline heuristic assessment was source-based, **25/40**. It is not a
post-change usability score.

| Nielsen heuristic | Baseline / 4 | Main finding |
| --- | ---: | --- |
| Visibility of system status | 2 | Initial request failures could remain skeletons. |
| Match with the real world | 3 | Job-search navigation is coherent; some configuration needs purpose and grouping. |
| User control and freedom | 2 | Changing settings destinations could discard edits. |
| Consistency and standards | 2 | Individual writes and page-level saves had unclear scopes. |
| Error prevention | 2 | Archive and deletion policies shared one undifferentiated group. |
| Recognition over recall | 3 | Long optional forms and credential lists obscure the relevant choice. |
| Flexibility and efficiency | 3 | Useful search/bulk tools; configuration requires excessive scrolling. |
| Aesthetic and minimalist design | 3 | Consistent tokens, with competing global and local actions. |
| Error recovery | 2 | Some pages lack retry; failed API-key saves close their editor. |
| Help and documentation | 3 | Good integrity guidance; sparse configuration introductions. |

The baseline detector found one `side-tab` warning in `StageFlowChart.tsx`.
Its colored border associates stage-flow rates with their Sankey status colors;
that existing semantic use was retained. The baseline layout scan found no
mechanical issues. These scans cannot establish usability or accessibility.

## Priorities addressed

| Priority | Before | Result |
| --- | --- | --- |
| P1 | Settings navigation silently loses edits. | One workspace guard protects SaveBar forms, unfinished tag input, agent guidance, and password-manager edits. Keep editing retains the draft; discard follows the intended destination. Reload/close uses the browser's unload warning. The registry stores booleans, never form values or credentials. |
| P1 | An API-key editor closes before its request succeeds. | The editor waits for success, retains the entered value on failure, exposes the error, and supports retry. Other actions are disabled during the request. |
| P1 | Failed requests resemble loading or empty results. | Shared loading/error/retry feedback covers settings and dashboard, Profile, boards, and analytics. Settings keep an existing editable draft during a failed background refresh. |
| P2 | Global discovery actions compete with configuration and preparation. | The toolbar appears on job-search workspaces. Profile, conversations, analytics, settings, account, and admin keep their own task actions. Pull is the toolbar's filled primary action; Refresh is secondary. |
| P2 | Flat fields, narrow columns, and long optional forms impede scanning. | Shared section headings explain decisions; container queries follow actual panel width; optional application sections expand without unmounting their fields. Required-field validation opens a collapsed section before focusing its invalid input. |

## Settings inventory

| Destination | Layout and interaction |
| --- | --- |
| Search | Role targets, location/work preferences, salary/experience, and disclosed relevance tuning. Unfinished tags are guarded; location normalization still completes before save. An inverted experience range is explained and cannot be saved. |
| Sources | Shared page purpose and explicit immediate-save scope. Connector failures offer retry. Source-limit inputs have usable touch targets. |
| Pruning | Restorable archive rules and permanent retention are separate decision groups. Inputs adapt to the panel width. |
| Review panel | Fast/Deep remain separate saved rosters with the existing switch confirmation. Fields use container breakpoints. The horizontally scrolling reviewer table is named and keyboard-focusable. |
| Style guide | Visible editor label, concise Markdown guidance, stable title, and retry. |
| Rendering | Uploads apply individually; selected layout and page options save together. Template-list failure has its own retry. |
| Application profile | Contact details lead. Structured records and optional answer groups expand in place. Existing values and unknown/blank semantics are preserved. Validation reveals collapsed required fields. |
| Password manager | Shared page shell and edit protection, preserving password custody, revision/conflict handling, and its existing individual save operations. |
| Email & notifications | Distinguishes mailbox tracking from notification delivery. Optional OAuth credentials use the reliable individual-key editor. |
| API keys & models | AI provider keys, model tiers, and discovery/service access have distinct groups and save-scope guidance. Gmail OAuth stays on the email page. |
| Agent prompts | Each editor saves separately. Search and refetch preserve unsaved guidance; initial failures offer retry. |
| Backup | Export/import/reset purpose, visible bundle-read progress, and retry when the section registry cannot load. Existing preview-before-apply behavior remains. |

Other reviewed destinations include Dashboard, Profile/Documents, Profile/Skills,
Coach, Interview, Career Lab, Scout, Triage, Shortlist, Pipeline, Match Gap,
Applications, Analytics, Account, Administration, Cost quotas, Provider routing,
all five setup steps, and all six authentication forms. Existing task-specific
boards, conversations, approval flows, and authentication layouts were retained.
Their shared shell now restores the top of a new destination and focuses its main
landmark; hash destinations keep their anchor behavior. Sticky settings and
conversation rails follow the measured chrome height.

## Reusable patterns

- `SettingsPage`: title, full-width purpose, actions, and recoverable query state.
  A background error does not replace children or erase a draft.
- `SettingsSection`: a named decision group with heading, explanation, and fields;
  use separation and proximity instead of another nested card.
- `SettingsDisclosure`: optional fields stay mounted when collapsed. A form with
  required disclosed fields must reveal their details ancestors on invalid input.
- `QueryFeedback` / `PageFeedback`: distinguish a failed request from a valid
  empty dataset; provide Retry and retain a page title during loading/error.
- `useUnsavedChanges`: register dirty/saving status in the shared provider. SaveBar
  registers automatically; individual editors register their own state.
- `DeferredDialogBody`: Pull and Reprocess now use the existing on-demand form
  pattern. Closing keeps their draft state and their form dependencies stay out
  of the cold dashboard download.

All new copy has authored English and Simplified Chinese translations. Existing
semantic colors, fonts, control primitives, and light/dark tokens remain the
visual authority.

## Verification

- **1,177 unit tests passed**, including navigation cancellation, multiple dirty
  editors, reload protection, failed-key retry, initial-load recovery, and draft
  retention during a failed background refresh.
- **102 browser checks passed** across the 40 route states and settings workflows.
  Coverage includes English/Chinese, light/dark, 375/768/1024/1440px configuration
  views, keyboard table access, dirty navigation, save/discard, collapsed-field
  validation, and deferred form-state retention.
- **3 additional Profile browser checks passed**, including long names in both
  themes and 200% text at 320/768/1280/1920px.
- Production build, TypeScript, ESLint, and localization checks passed. The
  localization catalog covers 2,353 UI literals and 64 backend progress labels.
- The mechanical scan of 38 changed production markup files returned no findings;
  the final shell refinement also passed the active design hook.
- The coordinator visually inspected Search, Application profile, Review, API
  keys/models, Pruning, Email, Dashboard, and Profile, including narrow Chinese
  dark mode and the intermediate width with both navigation rails visible.

Production gzip measurements: initial JavaScript **261,769 bytes**, cold Dashboard
**346,000**, cold Pipeline **388,276**, largest deferred chunk **103,229**. All
regression ceilings pass. The existing 200 KB initial target remains unmet.
These are download sizes, not latency measurements.

Browser checks use controlled API fixtures. Live provider calls, OAuth sign-in,
mail delivery, and production credentials were not exercised. Automated checks
and the rendered review do not establish a complete accessibility audit.

The baseline assessments and detailed machine reports are local artifacts under
`output/ui-refactor/`. No overlay was injected. Temporary review servers are
stopped after verification; the browser viewport override is reset.

Questions skipped: the user already requested implementing the review across all
pages and explicitly prioritized user-facing settings/configuration.
