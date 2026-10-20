# 002 — Refine agent state feedback

- **Status**: DONE
- **Commit**: fa971f7d
- **Severity**: MEDIUM
- **Category**: Accessibility, interruptibility, state indication
- **Estimated scope**: Shared CSS, chat activity/progress, Scout disclosures, shared loaders

## Problem

`web/src/components/chat/parts/ToolPart.tsx:20` currently has:

```tsx
<Loader2 className="size-3.5 animate-spin text-primary" aria-hidden="true" />
```

The caret in `TextPart.tsx:12`, shared `ui/spinner.tsx:6`, and Sonner loader
also run continuously without reduced-motion handling. Tool and reasoning
panels combine `transition-[opacity,transform]` with independent translate
utilities and permanent `will-change`; their reduced-motion phase selectors
are inconsistent. `HintsPart.tsx:30` snaps its body open:

```tsx
<CollapsibleContent className="overflow-hidden data-starting-style:h-0 data-ending-style:h-0">
```

## Target

Continuous motion uses `motion-safe:animate-spin` or
`motion-safe:animate-pulse`. Reduced mode keeps static icons, status text,
and the caret; it does not introduce artificial delays or progress.

```css
.agent-disclosure {
  opacity: 1;
  transform: translateY(0);
  transition: opacity 160ms var(--ease-out-strong), transform 160ms var(--ease-out-strong);
}
.agent-disclosure:is([data-starting-style], [data-ending-style]) {
  opacity: 0;
  transform: translateY(-4px);
}
.agent-status-enter { opacity: 1; transition: opacity 160ms var(--ease-out-strong); }
@starting-style { .agent-status-enter { opacity: 0; } }
@media (prefers-reduced-motion: reduce) {
  .agent-disclosure,
  .agent-disclosure:is([data-starting-style], [data-ending-style]) {
    transform: none;
    transition: opacity 160ms var(--ease-out-strong);
  }
}
```

The token resolves to `cubic-bezier(0.23, 1, 0.32, 1)`; no new curve is needed.

## Repo conventions to follow

`web/src/components/ui/dialog.tsx` uses Base UI start/end attributes and
CSS transitions. Existing `agent-artifact-enter` in `index.css` demonstrates
`@starting-style`. Do not replay any entrance when text deltas arrive.

## Steps

1. Add the exact CSS above to `web/src/index.css`.
2. Use `agent-disclosure overflow-hidden` on mounted panels in
   `ToolPart.tsx`, `ReasoningPart.tsx`, `HintsPart.tsx`,
   `web/src/features/scout/ProposalRail.tsx`, and `ProposalCard.tsx`.
   Preserve panel padding/content classes and controlled disclosure state.
   Retain existing `keepMounted` on tool/reasoning/Scout panels. Keep the
   hints panel's default unmount behavior; Base UI retains it during exit.
   Remove old translate/transition/will-change classes. Hints chevron uses
   160ms strong easing.
3. Add `agent-status-enter` only to terminal tool icons, the run-progress
   shell, and its settled checkmark. Do not key/remount prose or status
   labels on every event. Keep notices, errors, and current/total factual.
4. Gate continuous motion in ToolPart, TextPart, shared Spinner, Sonner, and
   ChatRunProgress with `motion-safe` as described above.

## Boundaries

Do not change `web/src/lib/chat/events.ts`, stream ordering, cancellation,
retry/reconnect timing, or backend agent loops. No height tweening, hover
movement, permanent `will-change`, per-token animation, or new dependencies.

## Verification

Run `npm run test:run -- src/components/chat src/lib/chat` and
`npx.cmd --no-install playwright test e2e/agent-motion.spec.ts --workers=1`
from `D:\Fun\resume-agent\web`. Open/close tool, reasoning, and hints panels
rapidly. At 10% playback, confirm smooth reversal and no restart jump.
Inspect reduced-motion computed styles during entry and exit: no transform,
opacity transition retained. Test text → tool start → tool success/failure →
settled → completed, and cancellation with a pending tool. Icons/caret stop
looping at terminal states while partial prose remains available.

Done when all states remain legible, accessible, and interruptible in English,
Chinese, light/dark themes, and a 390px viewport.
