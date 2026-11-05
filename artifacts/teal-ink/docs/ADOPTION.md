# Adopt and refactor

## Choose the smallest useful integration

| Situation | Bring over |
| --- | --- |
| Existing component library | `styles/tokens.css`; optional font; map semantics into the current theme |
| Plain HTML or another framework | `styles/index.css`; native HTML with the documented classes |
| React 19 project | Core CSS + copy `adapters/react.tsx`; follow `examples/Workspace.tsx` |
| Tailwind v4 project | Tokens + `adapters/tailwind-v4.css`; keep existing interaction components |
| Design exploration | Open `preview.html`; edit token JSON and regenerate |

This is a versioned copy-in artifact. It has no runtime dependency for HTML/CSS
use, and does not require the original Resume Tailor repository. The optional
React source needs React 19 and the host's TypeScript/build setup. The optional
Tailwind adapter needs a v4 build; do not add it directly as a browser stylesheet.

## Plain CSS

Preserve the directory tree when copying it, because the font and CSS imports
use relative paths. Apply `.ti-root` to the full app root or the region adopting
the design system. A `data-ti-theme` boundary chooses its local theme.

```html
<section class="ti-root" data-ti-theme="dark">
  <div class="ti-card">
    <h2 class="ti-card-title">Review details</h2>
    <p class="ti-muted">Keep the context close to the action.</p>
  </div>
</section>
```

Set `data-ti-theme` on `<html>` for a whole application. Omit it for the operating
system default, or set `"system"` explicitly. `"light"` and `"dark"` are stable
choices. Existing `.dark` roots work when the class is on `<html>` or the actual
`.ti-root` boundary; use `data-ti-theme` for nested theme islands. Explicit theme
attributes take priority over class mode. CSS handles later system changes.

Theme preferences, storage, and hydration belong to the host app. This kit's
preview demonstrates guarded local storage, but its script is not a product
theme provider. Do not copy `preview.js` or `styles/preview.css` into the app.

## React 19

Copy the adapter into the host source tree and adjust the import location.
It uses native props, `useId`, and React 19's ref-as-a-prop behavior from the
[official React documentation](https://react.dev/reference/react/forwardRef).
No component-library runtime or path alias is required.

```tsx
import { Button, TextField, ThemeBoundary } from "./design-system/react";
import "./design-system/styles/index.css";

<ThemeBoundary theme="dark">
  <form className="ti-stack" onSubmit={submit}>
    <TextField label={copy.name} name="name" required hint={copy.nameHint} />
    <Button type="submit" loading={saving} loadingLabel={copy.saving}>
      {copy.save}
    </Button>
  </form>
</ThemeBoundary>
```

The adapter supplies primitives, not business state. Keep localization,
asynchronous work, validation policy, routing, and actual approval in the host.
Use `examples/Workspace.tsx` as a small native form/dialog composition. It gives
each dialog its own title/description IDs so multiple instances remain distinct.

## Tailwind v4

Import the adapter after the tokens in the host's CSS entry point:

```css
@import "tailwindcss";
@import "./vendor/teal-ink/styles/fonts.css";
@import "./vendor/teal-ink/styles/tokens.css";
@import "./vendor/teal-ink/adapters/tailwind-v4.css";
```

```html
<main class="ti-root bg-ti-background text-ti-foreground" data-ti-theme="dark">
  <article class="rounded-ti-lg bg-ti-card p-4 shadow-ti-card">
    <h2 class="font-ti-ui font-semibold">Workspace</h2>
  </article>
</main>
```

The adapter uses the official [Tailwind theme variable approach](https://tailwindcss.com/docs/theme#referencing-other-variables):
`@theme inline` binds generated utilities to locally resolved CSS variables.
Its color/font/radius/shadow utility names are prefixed with `ti-`. The optional
custom `dark:` variant recognizes `.dark`, dark theme attributes, and gateway
attributes. If the host already owns its `dark:` variant, keep that definition
and copy only the adapter's `@theme inline` block. Prefer semantic utilities for
themeable colors; their values already follow `system` theme changes. A manual
dark variant does not infer system mode, or isolate itself from an outer dark
ancestor. Avoid relying on it inside opposite-theme nested islands.

## Customize with intent

For a permanent fork, edit the source token JSON and regenerate both exports.
Change the semantic primary alias in **each** theme instead of changing every
button. Keep paired on-primary and hover/active colors readable. Primitive
palette steps added to complete the teal scale are documented in the source
audit; they are available for a future fork, not a requirement to use more color.

For a local theme or one component, override at the same element that declares
the theme boundary. CSS aliases resolve where they are declared.

```css
/* Load after tokens.css. Uses existing tokens; no new raw color values. */
.project-theme[data-ti-theme="light"] {
  --ti-color-primary: var(--ti-p-color-teal-700);
  --ti-color-primary-hover: var(--ti-p-color-teal-600);
  --ti-color-primary-active: var(--ti-p-color-teal-700);
  --ti-button-radius: var(--ti-radius-pill);
}
```

Apply `class="ti-root project-theme" data-ti-theme="light"`. This changes the
local palette and button shape while component aliases resolve at that boundary.
For a per-component override on a descendant, override `--ti-button-bg` and its
matching `--ti-button-fg` directly. A semantic override on a child that is not a
theme boundary will not necessarily rebind inherited component aliases.

## Refactor an existing project incrementally

1. Inventory its actual screens, states, themes, locales, and interaction
   primitives. Record current behavior before changing shared components.
2. Bring over tokens and map the host's semantic names. Keep route/data behavior
   and accessible primitives intact. Start with a representative real workflow.
3. Align the primitive controls, cards, page headings, and status tones. Follow
   with complete compositions: header, metrics, compact rows, review, and result.
4. Replace repeated literal values with semantic/component references. Keep
   domain colors and workflow terminology explicit rather than guessing them.
5. Check the real product with long names, empty/loading/error states, narrow
   widths, English/Chinese, both themes, 200% text, keyboard, and touch targets.
6. Remove obsolete styles only after adoption is verified. Record intentional
   differences and update the destination fork's changelog.

## Source-to-portable map

| Resume Tailor convention | Portable equivalent |
| --- | --- |
| `--background`, `--foreground` | `--ti-color-background`, `--ti-color-foreground` |
| `--primary`, `--primary-foreground` | `--ti-color-primary`, `--ti-color-primary-foreground` |
| `--card-shadow`, `shadow-card` | `--ti-shadow-card`, `.ti-card` |
| `.tone-panel` / `.tone-chip` | `.ti-alert` / `.ti-badge` with `data-tone` |
| `PageHeader`, `MetricRow` | Portable wrappers or `.ti-page-header`, `.ti-metrics` |
| Profile skill/source rows | `.ti-rows` + `.ti-row` with container-based columns |
| `.command-panel` | `.ti-command-panel` + `.ti-nav-item[aria-current]` |
| `.auth-shell` | Scoped `data-ti-theme="gateway"` |

Do not replace source imports with the artifact wholesale. The original product
has many specialized Base UI/shadcn components and business interactions that
are intentionally outside this portable snapshot.

## Version and distribution

Keep `source-manifest.json` and the MIT/OFL notices with copied artifacts. Track
your fork's changes in `CHANGELOG.md`. Token removals and contract changes need
a major version; compatible additions are minor; corrections are patch changes.
Keep a deprecated alias through at least one release cycle when renaming tokens.

The supplied package is private. To create an internal package later, choose
your own scope, build/type-check the React entry points as needed, define exports
and supported browsers, then validate the consuming app before publication.
No registry or design-tool publication is performed by this artifact.
