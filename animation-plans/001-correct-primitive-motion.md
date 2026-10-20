# 001 — Correct primitive motion

- **Status**: DONE
- **Commit**: fa971f7d
- **Severity**: HIGH
- **Category**: Performance, physicality, accessibility
- **Estimated scope**: Shared CSS, button/sheet primitives, five existing press consumers

## Problem

`web/src/components/ui/button.tsx:7` contains these exact class fragments:

```text
transition-[background-color,border-color,color,box-shadow,transform]
active:not-aria-[haspopup]:scale-[0.98] motion-reduce:transform-none
```

Tailwind 4's active utility changes `scale`, which is not in that explicit
transition list. Resetting `transform` leaves the independent scale untouched.
`web/src/components/ui/sheet.tsx:54` similarly combines
`transition-[opacity,transform]` with independent `translate` utilities. Its
side-specific phase selectors also outrank its reduced-motion reset.

## Target

Button feedback uses `transition-[background-color,border-color,color,box-shadow,scale]`,
`duration-150 ease-out-strong`, and
`motion-safe:active:not-aria-[haspopup]:scale-[0.98]`. Preserve all other classes.

Add `--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1)` alongside the existing
`--ease-out-strong: cubic-bezier(0.23, 1, 0.32, 1)` in `web/src/index.css`.
Give the sheet popup a `sheet-panel` class and move its motion into CSS:

```css
.sheet-panel {
  opacity: 1;
  transform: translate(0);
  transition: opacity 200ms var(--ease-out-strong), transform 240ms var(--ease-drawer);
}
.sheet-panel:is([data-starting-style], [data-ending-style]) { opacity: 0; }
.sheet-panel[data-side="right"]:is([data-starting-style], [data-ending-style]) { transform: translateX(100%); }
.sheet-panel[data-side="left"]:is([data-starting-style], [data-ending-style]) { transform: translateX(-100%); }
.sheet-panel[data-side="bottom"]:is([data-starting-style], [data-ending-style]) { transform: translateY(100%); }
.sheet-panel[data-side="top"]:is([data-starting-style], [data-ending-style]) { transform: translateY(-100%); }
@media (prefers-reduced-motion: reduce) {
  .sheet-panel,
  .sheet-panel[data-side]:is([data-starting-style], [data-ending-style]) {
    transform: none;
    transition: opacity 160ms var(--ease-out-strong);
  }
}
```

## Repo conventions to follow

`web/src/components/ui/dialog.tsx:56` already transitions the independent
`scale` property correctly. Keep Base UI responsible for mounting, focus,
phase attributes, cancellation, and unmount timing. No animation library.

## Steps

1. Correct the button class fragments above.
2. Remove all motion utilities from the sheet popup while retaining its
   existing per-side layout utilities, close button, portal, and attributes.
   Apply the exact CSS above; retain the backdrop's 150ms opacity fade under
   reduced motion too.
3. In `web/src/features/job/CompanyIntelligenceEvidence.tsx`, change explicit
   press transition lists from `transform` to `scale` and gate active scale
   with `motion-safe`. Gate the local active override in
   `EvidencePortfolioDisclosure.tsx` the same way.
4. In `web/src/features/dashboard/ActionQueue.tsx`, use
   `transition-[box-shadow,scale] duration-150 ease-out-strong` and
   `motion-safe:group-active:scale-[0.985]`. Preserve 100ms press timing.
5. Remove scale feedback from core navigation in `web/src/app/AppLayout.tsx`
   and `web/src/features/dashboard/QuickAccess.tsx`; retain color/shadow
   feedback. Remove `transition-transform` from AppLayout's keyboard skip
   link so focus is immediately visible.

## Boundaries

No dependencies, route changes, new hover movement, sidebar geometry changes,
backend changes, or altered dialog focus/close semantics. If the excerpts
have drifted, reconcile the plan before editing.

## Verification

From `D:\Fun\resume-agent\web`, run `npm run lint`, `npm run build`, and
`npx.cmd --no-install playwright test e2e/agent-motion.spec.ts --workers=1`.
Browser CSS must name `scale` in the button's transition properties. Holding a
press should ease toward 0.98; reduced motion must leave scale at 1/none.
Open/close the mobile sidebar rapidly: it should reverse toward its own edge,
settle within 240ms, and return focus. At 10% playback, check that entry and
exit use the same axis. In reduced motion, inspect both start/end phases:
transform must be `none`, with an opacity transition still present.

Done when computed CSS and interaction checks pass without new focus or
navigation regressions.
