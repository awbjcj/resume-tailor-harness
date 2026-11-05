# Source audit

Extracted 2026-11-04 from Resume Tailor commit
`34d69affda2f489daf38a6d1ab12333a126c45f7`. Source SHA-256 fingerprints and the
original light/dark/auth token maps are retained in `../source-manifest.json`.
This is an independent portable snapshot; the product does not import it.

## What defines the source style

| Source file | Retained design decision |
| --- | --- |
| `web/src/index.css` | Exact semantic colors, 0.5rem radius and multipliers, two-part shadows, stage colors, tone blends, motion curves, 72px grid |
| `web/src/features/auth/auth.css` | Isolated dark gateway, mint primary, deep ink, workflow traces, focused entry |
| `web/src/components/ui/button.tsx` | Primary/outline/secondary/ghost/destructive hierarchy; 40px default; 150ms response; press scale |
| `web/src/components/ui/input.tsx` | Connected field material, 40px control, readable input text, focus and invalid states |
| `web/src/components/ui/card.tsx` | Modest radius, 16px default padding, contact shadow, contextual footer |
| `web/src/components/ui/badge.tsx` | Compact pill labels; meaning separate from the surrounding surface |
| `web/src/components/ui/tabs.tsx` | Quiet rail and active emphasis; host primitives retained for actual tabs |
| `web/src/components/PageHeader.tsx` | Wrapping actions; tight heading tracking; bottom rule; resilient long copy |
| `web/src/components/MetricRow.tsx` | Unboxed summary metrics, tabular numbers, spacing-led hierarchy |
| `web/src/app/AppLayout.tsx` | Command navigation with a leading active indicator and grouped sections |
| `web/src/features/profile-skills/SkillCompactView.tsx` | Full-width compact rows; stable columns; wrapping chips instead of uneven tiles |

The extraction audit inspected source code. Its browser evidence exercises the
portable preview, not the production application's complete rendered UI.

## Deliberate portability refinements

- **Namespacing:** all public classes/variables use `ti-` / `--ti-` so adoption
  can be incremental. Product routes, data contracts, and job-specific behavior
  are excluded. Stage colors remain available with neutral numbered hooks.
- **Three layers:** source flat semantic values become typed primitives,
  semantic aliases, and component aliases. Theme documents retain exact source
  colors instead of substituting a generic cyan or slate palette.
- **Control boundaries:** decorative `border` and original `input` colors are
  preserved. Actual field/outline control appearance uses `field-border`, which
  has enough contrast to distinguish the control from the surface.
  `on-muted` provides readable secondary copy directly on muted fills while
  retaining the source's exact `muted-foreground` token for cards and canvas.
- **Fonts:** source Geist remains the interface face. Code uses a true system
  monospace stack rather than the source's Geist alias. Chinese uses explicit
  fallback families. Only the licensed Latin font is bundled.
- **Themes:** light/dark values are retained. Gateway semantics are completed
  for cards, popovers, and sidebar roles so it can be reused as a local preset.
  System changes and explicit nested boundaries work without a provider runtime.
- **Sizing:** default controls retain 40px proportions. Coarse-pointer minimums
  expand to 44px. Labels wrap and minimum heights grow with enlarged content.
- **Palette additions:** teal 100 `#d3f3f6`, 400 `#25bdcf`, and 950 `#0b191d`
  complete the optional 50–950 primitive scale. The modal overlay is authored.
  All other palette values come from the inspected source styles.
- **Interactions:** plain CSS and native HTML replace source-specific dependency
  chains in the portable examples. Complex dialogs, comboboxes, tabs, and menus
  should continue using a complete accessible primitive in the destination app.

## Keep this snapshot traceable

When refreshing, compare the fingerprinted files and inspect representative
source screens. Update the source commit, theme maps, refinements, and changelog.
Do not silently overwrite a consuming project's intentional token overrides.
Record whether verification covers the exported preview, a consuming app, or
the source product; these are separate evidence levels.
