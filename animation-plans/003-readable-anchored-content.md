# 003 — Keep content readable and anchored

- **Status**: DONE
- **Commit**: fa971f7d
- **Severity**: MEDIUM
- **Category**: Purpose/frequency, rendering continuity, accessibility
- **Estimated scope**: TextPart, ChatThread, SkillMatrix, CSS, localized labels, regression tests

## Problem

`web/src/components/chat/parts/TextPart.tsx:7` relies on a typography plugin
that is not installed:

```tsx
<div data-testid="chat-part-text" className="prose max-w-none text-base leading-7 dark:prose-invert prose-p:leading-7 prose-li:leading-7">
```

`web/src/components/chat/ChatThread.tsx:79` encloses growing prose in an atomic
live region:

```tsx
<div role="status" aria-label="Assistant response streaming">
```

Its bottom-follow effect depends only on `[messages, streaming, stuck]`.
Late image sizing, activity expansion, and viewport resizing can leave a
bottom-pinned reader behind. `SkillMatrix.tsx:20` delays all chips with:

```tsx
className="skill-chip rise-in"
style={{ "--rise-i": index } as React.CSSProperties}
```

## Target

Readable content stays stationary. No new text, route, history, or skill-chip
animation. Streamed prose is outside live regions; compact existing status
announcements remain. Wide Markdown scrolls locally and is keyboard reachable.

Use a `chat-markdown` class with `min-width: 0; overflow-wrap: anywhere`.
Headings have weight 650, line-height 1.4, and block margins 1.25em/0.5em;
h1 is 1.375rem, h2 1.125rem, h3–h6 1rem. Ordered/unordered lists use
decimal/disc and 1.5em inline-start padding. Text blocks have 0.85em block
margins, with no outer first/last margins. Code uses the existing mono font
and themed muted surface. Preformatted code retains whitespace, gets
`overflow-x: auto`, padding 0.875rem/1rem, and a 1px themed border.
Tables live in a `max-width: 100%; overflow-x: auto` bordered wrapper;
cells use a minimum 8rem width and 0.5rem/0.75rem padding. Images fit their
container at natural aspect ratio. Do not change Markdown URL sanitization.

## Repo conventions to follow

`web/src/index.css:707` explicitly styles `jd-markdown`; extend the same
dependency-free approach for conversation/draft content. TextPart is also
used by audio transcripts and Career Lab drafts. Existing ChatMessage
memoization demonstrates the need to avoid reparsing unchanged text.

## Steps

1. Memoize TextPart with React `memo`; move the remark plugin array and
   Markdown component mapping outside the render function.
2. Add custom `table` and `pre` components. Table wrapper has `role="region"`,
   `aria-label="Table"`, `tabIndex={0}`, and `chat-markdown-scroll`; pre has
   `aria-label="Code block"` and `tabIndex={0}`. Keep table semantics and
   all Markdown children intact. Add the explicit CSS values above and
   visible focus outlines using the existing ring token.
3. Register Table/Code block in `web/src/i18n/auto-catalog.json` with
   translations 表格/代码块. Generate runtime catalogs with
   `npm run i18n:generate`; remove the obsolete streaming wrapper label.
4. Replace the stream wrapper's `role`/label with
   `aria-busy={streamingActive}` and `data-testid="chat-streaming-response"`.
   Keep the existing Responding and tool lifecycle live statuses.
5. Attach a ref to the thread content. A `ResizeObserver` observes content
   and viewport only while `stuck` is true. Coalesce its callbacks into a
   single requestAnimationFrame, set scrollTop directly to scrollHeight,
   and disconnect/cancel on scroll-away or unmount. Preserve the existing
   data-change effect and Jump to latest control. Never smooth-scroll deltas.
6. Remove `rise-in`, the per-chip index style, and unused index/baseIndex
   props from `web/src/components/SkillMatrix.tsx`. Keep grouping and all
   add-skill controls; do not alter the deliberately capped dashboard
   section entrance elsewhere.

## Boundaries

No backend, provider, reducer, routing, persistence, or agent behavior changes.
No unsafe HTML, sanitizer override, new dependency, synthetic token pacing,
or text movement. Reconcile drift against the stamped excerpts first.

## Verification

From `D:\Fun\resume-agent\web`: `npm run lint`, `npm run test:run`,
`npm run build`, and
`npx.cmd --no-install playwright test e2e/agent-motion.spec.ts --workers=1`.
Test long text, GFM tables, fenced code, lists, and multiple tool updates.
At 390px, document scrollWidth must stay within viewport width + 1px;
code/table overflow remains local and keyboard reachable. Expand a tall
activity while bottom-pinned: bottom gap returns below 2px. Scroll away,
then append text/resize: reading position remains unchanged. Jump returns
to the bottom. Inspect completed prose at 10% playback: it should not move.

Done when regression tests pass, settled/terminal feedback clears correctly,
and formatted content stays readable in both languages/themes.
