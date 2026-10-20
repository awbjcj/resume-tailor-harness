# UI and agent motion audit

Audited 2026-10-19 against `fa971f7d`. The user requested implementation as well
as discovery, so the vetted fixes were implemented on `fix/ui-agent-motion`.
The existing `plans/` contains guided-workspace plans; this directory preserves
the separate motion audit and its executable specifications.

## Recon

React 19, TypeScript, Tailwind 4, Base UI 1.9, `tw-animate-css`, CSS transitions;
no new dependencies. This is a functional career dashboard. Stream deltas,
navigation, and job/skill inspection are frequent; disclosures and sheets are
occasional. The existing strong curves are retained:

- `--ease-out-strong: cubic-bezier(0.23, 1, 0.32, 1)`.
- `--ease-in-out-strong: cubic-bezier(0.77, 0, 0.175, 1)`.
- Drawer curve: `--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1)`.

## Vetted findings

Locations below refer to the audited commit, before edits.

| # | Severity | Category | Location | Finding | Fix summary |
| --- | --- | --- | --- | --- | --- |
| 1 | HIGH | Performance, accessibility | `web/src/components/ui/button.tsx:7`; `web/src/components/ui/sheet.tsx:54` | Tailwind changes independent `scale`/`translate` while explicit transition lists target `transform`; movement snaps. Reduced-motion transform resets do not reset scale, and sheet phase selectors override its reduced-motion reset. | Transition `scale` for presses; use full transform strings for sheets; gate presses with `motion-safe`; stationary reduced-motion fades. |
| 2 | MEDIUM | Accessibility | `web/src/components/chat/parts/TextPart.tsx:12`; `ToolPart.tsx:20`; `web/src/components/ui/spinner.tsx:6` | Continuous caret and loader loops ignore reduced motion. | `motion-safe` on continuous animation; retain static icons and status text. |
| 3 | MEDIUM | Accessibility, content rendering | `web/src/components/chat/ChatThread.tsx:79` | The entire changing response is inside an atomic live status region. | Keep prose outside live regions and retain concise status announcements. |
| 4 | MEDIUM | Interruptibility, cohesion | `ToolPart.tsx:37`; `ReasoningPart.tsx:23`; `web/src/features/scout/ProposalCard.tsx:91` | Disclosure transitions target transform while state utilities change translate; reduced-mode phase offsets can survive. Persistent `will-change` is unnecessary. | Shared `agent-disclosure`: 160ms transform/opacity transitions, phase-aware reduced-motion override, no persistent promotion. |
| 5 | MEDIUM | Purpose, speed, function | `web/src/components/SkillMatrix.tsx:20`; `web/src/index.css:635` | Skill 31 stays invisible for 1080ms, including its interactive add control. | Render functional skill chips immediately; remove per-chip delay bookkeeping. |
| 6 | MEDIUM | Content rendering | `web/src/components/chat/parts/TextPart.tsx:7`; `ChatThread.tsx:50` | Typography-plugin classes have no installed plugin; wide Markdown lacks local scroll surfaces. Bottom following only reacts to data changes, missing late layout changes. | Explicit semantic Markdown styles, memoized text rendering, accessible table/code overflow, and bottom-only resize anchoring. |

## Opportunities and gate results

| # | Location | Today at baseline | Purpose | Frequency | Suggested motion |
| --- | --- | --- | --- | --- | --- |
| 1 | `web/src/components/chat/parts/HintsPart.tsx:30` | Hints snap open while the chevron rotates. | State indication | Occasional | Shell only: `transform: translateY(-4px)` and `opacity: 0` to `translateY(0)` and `1`, both 160ms `cubic-bezier(0.23, 1, 0.32, 1)`; reverse using Base UI phase attributes. Reduced motion keeps a 160ms opacity fade with `transform: none` in both phases. **Speed:** 160ms passes. **Function:** hint text stays stationary after entry; no height tween. No hover motion. |
| 2 | `web/src/components/chat/parts/ToolPart.tsx:22`; `ChatRunProgress.tsx:13` | Completion icons and the progress shell replace state abruptly. | Preventing a jarring change | Tens/day | Opacity only: 0 to 1, 160ms `cubic-bezier(0.23, 1, 0.32, 1)` using `@starting-style`. Reduced motion retains that gentle fade. **Speed:** 160ms passes. **Function:** no movement, staged text, or delayed interaction. No hover motion. |

## Rejected candidates

- Per-token text reveals, message entrances, and smooth scrolling on every SSE
  delta: **rejected by frequency/function**. Frequent readable content must not
  move or acquire artificial latency.
- Session navigation, route entrances, and proposal ledger row staggers:
  **rejected by frequency/function** and the existing guided-workspace scope.
- Desktop sidebar geometry and keyboard skip-link motion: **rejected by the
  keyboard gate**. Preserve immediate sidebar geometry and make skip focus
  immediate. Core navigation keeps color feedback only.
- Job-skill entrance cascades and animated analytics drawing: **rejected by
  function**. Information and controls should be immediately readable.
- More bouncing or celebrations on completed tool calls: **rejected by
  frequency/purpose**. Ordinary agent work does not consume the rare delight
  budget.

## Plans and execution order

| Order | Plan | Severity | Status | Dependencies |
| --- | --- | --- | --- | --- |
| 1 | [001 — Correct primitive motion](001-correct-primitive-motion.md) | HIGH | DONE | None |
| 2 | [002 — Refine agent state feedback](002-refine-agent-state-feedback.md) | MEDIUM | DONE | 001 tokens |
| 3 | [003 — Keep content readable and anchored](003-readable-anchored-content.md) | MEDIUM | DONE | 002 disclosure behavior |

The interface needs little additional motion. The largest improvement is
repairing the property mismatch and reduced-motion paths; the most useful new
motion is the short hints disclosure bridge. Each linked plan can be executed
independently against its stamped baseline with `improve-animations execute
<plan>`; the implementation in this branch has passed the checks below.

## Validation

Run from `D:\Fun\resume-agent\web`:

| Check | Result |
| --- | --- |
| `npm run lint` | Passed; the final browser-test edits also passed targeted ESLint. |
| `node node_modules/vitest/vitest.mjs run --maxWorkers=4` | 211 files, 929 tests passed. |
| `npm run build` | Translation validation, TypeScript, and Vite production build passed. |
| `npx.cmd --no-install playwright test e2e/agent-motion.spec.ts e2e/scout-ledger.spec.ts e2e/board-ux.spec.ts e2e/career-lab.spec.ts --workers=2 --reporter=line` | 20 tests passed. |
| Stronger scroll-away assertion, repeated after waiting through two animation frames | Both English/light and Chinese/dark mobile scenarios passed. |
| Read-only implementation review | Both audit reviewers found no remaining actionable defects. |

Browser checks cover 390px mobile, both languages/themes, local Markdown
overflow, bottom following after disclosure expansion, preserving scroll-away
position, rapid disclosure reversal, real active button scaling, stationary
reduced-motion sheet phases, success/settlement, and cancellation of pending
tools. Screenshots were visually inspected at
`web/output/agent-motion-en-no-preference.png` and
`web/output/agent-motion-zh-CN-reduce.png` (local generated artifacts).

The existing job-assistant browser assertion now checks the stable settled-state
copy. Its finite SSE fixture closes without a final persistence event, which
legitimately changes the status headline to Reconnecting before the assertion.
No stream/reconnect implementation was changed.

Automated checks exercise real rendered CSS and the stream reducer with
deterministic SSE fixtures. Manual assistive-technology, real-device gesture,
and 10% playback feel checks are not claimed. Existing Vite configuration/chunk
size notices and jsdom canvas notices remain non-failing tooling output.
