# The design system

Teal & Ink is a practical workspace language. Its hierarchy comes from
alignment, spacing, type, and subtle material changes. Accent color identifies
actions and meaning without competing with the work.

## Foundations

| Decision | Light | Dark | Purpose |
| --- | --- | --- | --- |
| Canvas | `#f6f8fb` | `#121416` | Quiet working background |
| Surface | `#ffffff` | `#181b1f` | Cards, dialogs, and grounded content |
| Foreground | `#182026` | `#eef4f7` | Main readable ink |
| Primary | `#08708a` | `#5bd8e7` | Forward action and active navigation |
| On primary | `#ffffff` | `#102023` | Label inside a filled action |
| Muted ink | `#65717c` | `#a7b1bb` | Secondary copy, never disabled by default |
| Accent surface | `#e6f7fa` | `#17373c` | Selected, contextual emphasis |
| Danger | `#bd2d46` | `#ff6b82` | Errors and destructive intent |
| Warning | `#8a6500` | `#e6b94d` | Review, uncertainty, and attention |
| Success | `#1f7a4d` | `#43d19e` | Verified or completed state |
| Information | `#3867d6` | `#86a9ff` | Supporting guidance |

Gateway uses `#080f15` canvas, `#111d26` surface, and `#a4ecdc` action mint.
It is an intentional local theme for entry or focused onboarding.

The chart ramp is for visualization fills. It is not a text palette. Stage
colors preserve the source's neutral/teal/green/indigo/ochre/crimson sequence.
Map those stages to the destination's real workflow before using their labels.

## Token architecture

| Layer | JSON example | CSS example | Ownership |
| --- | --- | --- | --- |
| Primitive | `primitive.color.teal.600` | `--ti-p-color-teal-600` | Raw foundational value |
| Semantic | `semantic.color.primary` | `--ti-color-primary` | Theme and purpose |
| Component | `component.button.bg` | `--ti-button-bg` | Component-specific choice |

Semantic tokens alias primitives; component tokens alias semantics. Keep those
boundaries when adding tokens. Dark and gateway documents replace semantic
values at the same paths. The generated CSS repeats aliases at theme boundaries
so nested themes bind components to the correct local values.

Every token has a type and description. DTCG dimensions use `px` or `rem` objects,
colors use sRGB components, shadows use typed composites, and easing uses cubic
Bézier arrays. Tracking is a unitless number multiplied by `1em` in CSS.

## Typography, space, and material

| Category | Scale or rule |
| --- | --- |
| Typeface | Geist Variable; CJK system fallbacks; true system monospace for code |
| Text | 12 / 14 / **15 body** / 16 input / 18 / 20 / 24 / 30 / 36px |
| Weight | 400 regular, 500 medium, 600 semibold, 650 strong, 700 bold |
| Leading | 1.25 headings; 1.6 body; up to 1.8 explanatory copy |
| Tracking | −0.03em headings; −0.02em metrics; 0.16em short eyebrows |
| Spacing | 4px base with 2px/6px half steps; 8, 12, 16, 20, 24, 32, 40, 48, 64px |
| Radius | Base 8px; small 4.8px; medium 6.4px; large 11.2px; pills only for chips |
| Controls | 40px default; 36px small; 44px large and coarse-pointer minimum |
| Card padding | 16px default; compose 20–24px for larger working areas |
| Elevation | Two-part contact + ambient shadow, with a raised variant |
| Layout | Max 1440px; reading constraint 672px; optional 256px command rail |

The pixel values describe the 16px root baseline. The tokens use rem units for
text and spacing. Use minimum heights so wrapped labels can grow. Do not fix the
height of cards, fields, or action bars to fit sample copy.

## Component inventory

| Level | Implemented building blocks | Key behavior |
| --- | --- | --- |
| Atoms | Button, input/select/textarea, checkbox, badge, progress, spinner, skeleton | Native semantics; visible focus; loading and disabled states |
| Molecules | Labeled field, card/header/footer, tone alert, metric row, compact row | Label/description/error relationships; wrapping content |
| Organisms | Navigation, review dialog, table region, empty state | Current-location cues; native modal behavior; local overflow |
| Templates | Workspace header + metrics + rows; focused gateway | Consistent structure, independent of business data |

The core CSS implements appearance. Plain HTML supplies native behavior. The
React adapter wraps a subset and forwards native props/ref. Complex popovers,
comboboxes, tabs, and drawers should keep the host's established accessible
primitives; this kit does not ship replacement interaction engines for them.

### Button

`<button class="ti-button" type="button">Continue</button>`

| API | Values | Default |
| --- | --- | --- |
| CSS `data-variant`; React `variant` | primary, outline, secondary, ghost, danger, link | primary / attribute omitted in CSS |
| CSS `data-size`; React `size` | sm, md, lg, icon | md |
| Native `disabled` | boolean | false |
| React `loading`, `loadingLabel` | boolean; translated string | false; keeps children |

Use a real link with `.ti-button` for navigation and a real button for actions.
Icon-only controls need an accessible name. Use native `disabled` on buttons;
adding `aria-disabled` alone does not suppress events. Keep submission explicit:
the React wrapper defaults to `type="button"`.

### Fields

Wrap label, control, hint, and error in `.ti-field`. Connect the label's `for`
to the input ID, and connect hint/error IDs through `aria-describedby`. Add
`aria-invalid="true"` after validation. Include a clear corrective message and
focus the first invalid field on submit. Do not use a placeholder as a label.

React `TextField` accepts native input props plus `label`, `hint`, `error`, and
`fieldClassName`. It generates IDs using `useId`, preserves additional described
content, and accepts a native input ref. For select/textarea use the same HTML
field pattern with `.ti-select` / `.ti-textarea`.

### Cards, alerts, and badges

Cards compose `.ti-card-header`, content, and optional `.ti-card-footer`.
Use headings in document order; React `CardTitle` supports `as="h2|h3|h4"`.
Selected cards use `data-selected="true"`; appearance never supplies selection
semantics. Put a checkbox, radio, or real link/button inside as appropriate.

Alerts and badges accept `data-tone="success|warning|danger|info|stage-1…6"`.
React uses `tone`. They blend their surface against the card material. Keep
the state label visible and pair it with a symbol when useful. Static guidance
does not need `role="alert"`; reserve urgent live announcements for actual
errors. Decorative tone borders are intentionally below control contrast.

### Review dialog and tables

Use `<dialog class="ti-dialog">` with `showModal()`, a title connected by
`aria-labelledby`, explanatory content, and explicit cancel/confirm actions.
Reset `returnValue` before opening it again. Native Escape cancels; focus returns
to the opener. Nested dialogs or customized dismissal need separate validation.

Use a semantic table with column headers inside `.ti-table-wrap`. Wide technical
data can scroll locally. Give a scrollable region a name and keyboard access
when overflow needs to be reached. Do not make the whole page scroll sideways.

## State contract

| State | Visual treatment | Behavior |
| --- | --- | --- |
| Rest | Semantic surface, ink, and border | Normal native behavior |
| Hover | Small fill/shadow change, fine pointers only | No required information appears only on hover |
| Focus | 2px solid ring with 3px offset; no transition | Keyboard operation stays visible |
| Pressed | Explicit shade; 0.98 scale when allowed | Native activation; no movement under reduced motion |
| Disabled | 50% opacity | Native disabled; no activation |
| Loading | Spinner + retained or explicit loading label | `aria-busy`; prevent duplicate submission |
| Invalid | Danger border and corrective text | `aria-invalid`, described error, first-error focus |
| Selected | Quiet teal tint and outline | Native selection control or appropriate ARIA state |
| Empty | Brief explanation and one next action | Do not invent sample data in product screens |

Motion uses source durations of 150, 160, 180, 200, and 240ms. Prefer the supplied
strong ease-out curves. Reduced motion removes animation and transitions. Loading
must remain understandable through text even when its spinner stops moving.

## Responsive, accessible, and bilingual use

- Support 320px wide content and 200% text without page-level horizontal overflow.
  Use `minmax(0, 1fr)`, `min-width: 0`, logical properties, and wrapping labels.
- Compact rows gain a shared 12rem label column only when their container is at
  least 42rem. Keep labels above values when that space is unavailable.
- Main text pairs target 4.5:1; large text and essential control/focus indicators
  target 3:1. The field-border token is deliberately stronger than dividers.
  For secondary text directly on the muted fill, use `--ti-color-on-muted` or
  `.ti-on-muted`; source muted ink on that source fill narrowly misses 4.5:1.
- Keep keyboard order aligned with reading order. Provide a skip link in full
  shells. Use the host's tested primitives for more complex interactions.
- Preserve English/Simplified-Chinese meaning, required/optional states, approval
  scope, and success certainty. Keep API token names stable across locales.
- Use counts as supplementary information. Describe what the user can do next.
  Distinguish demo content from real progress or external effects.
- Check forced colors, touch targets, reduced motion, and screen-reader reading
  order in the destination product. Automated checks cover only part of access.

## Governance

Keep a local owner for the design-system fork. Patch releases fix defects without
changing a token's meaning; minor releases add compatible tokens/components;
major releases rename/remove public tokens or change component contracts. Keep
deprecated aliases for one release cycle and publish a migration mapping before
removal. Update the source audit when refreshing from the originating project.
