# Teal & Ink

A portable design system extracted from **Résumé Tailor** on 2026-11-04.
It preserves the project's teal actions, ink surfaces, Geist typography,
compact rows, shallow shadows, quiet grid, and clear review steps.

**Start with [the interactive preview](preview.html).** Open it directly in a
browser; fonts, scripts, and styles are local. No build, server, account, or
network connection is required. The preview has light/dark/system controls,
English/Simplified Chinese, working field validation, a review dialog, and a
searchable token explorer. Its content and counts are illustrative.

## Use it in another project

Copy this entire directory into your project, for example `vendor/teal-ink/`.
Keep its relative asset paths intact.

```html
<link rel="stylesheet" href="vendor/teal-ink/styles/index.css">

<main class="ti-root" data-ti-theme="light">
  <div class="ti-card ti-stack">
    <h1 class="ti-heading">Project workspace</h1>
    <p class="ti-muted">Review the next step.</p>
    <button class="ti-button" type="button">Continue</button>
  </div>
</main>
```

Use `data-ti-theme="dark"`, `"system"`, or `"gateway"` for another preset.
The mint-on-ink gateway is intended for focused entry and onboarding surfaces.
Use `.ti-root` for scoped base styles; `data-ti-theme` creates a theme boundary.
The CSS introduces no global element reset. The preview's layout styles are
separate from the reusable component stylesheet.

For existing components, import **only** `styles/tokens.css` and consume
`var(--ti-color-primary)`, `var(--ti-shadow-card)`, and related variables.
The bundled font is optional: import `styles/fonts.css` if desired.

## What is included

| Artifact | Purpose |
| --- | --- |
| [tokens/](tokens/base.tokens.json) | Typed primitive → semantic → component tokens; separate dark and gateway overlays |
| [styles/](styles/index.css) | Generated tokens, optional font, and framework-independent components |
| [React source](adapters/react.tsx) | Thin React 19 wrappers; native props, refs, connected field descriptions |
| [Tailwind v4 adapter](adapters/tailwind-v4.css) | Opt-in `bg-ti-primary`, `font-ti-ui`, and other namespaced utilities |
| [Workspace example](examples/Workspace.tsx) | Form → validation → review → explicit confirmation |
| [Design guide](docs/DESIGN-SYSTEM.md) | Principles, scales, components, states, accessibility, and content |
| [Adoption guide](docs/ADOPTION.md) | Copy-in setup, theming, customization, migration, and versioning |
| [Source audit](docs/SOURCE-AUDIT.md) | Exact source files, retained decisions, and deliberate refinements |
| [Agent brief](DESIGN-BRIEF.md) | A reusable instruction sheet for future projects and refactors |
| [Verification](docs/VERIFICATION.md) | What was checked and the limits of that evidence |

The tokens use the [DTCG 2025.10 format's typed values and aliases](https://www.designtokens.org/tr/2025.10/format/).
Theme overlays are ordinary token documents merged by this kit's build script;
they are not a claim of universal theme-import compatibility with design tools.

## Change the system

Edit `tokens/base.tokens.json`, `tokens/dark.tokens.json`, or
`tokens/gateway.tokens.json`, then use Node 22 or newer:

```sh
npm run build
npm run check
```

These commands have no npm dependencies and do not require `npm install`.
The build regenerates `styles/tokens.css` and the preview's local token catalog.
The check verifies references, layer boundaries, source-color fidelity,
contrast pairs, local links, and generated-file freshness.

For optional Chromium checks, see [verification instructions](docs/VERIFICATION.md).
The React source and Tailwind adapter are opt-in integration sources, not a
precompiled or published component package. `package.json` is private to avoid
accidental publication. This snapshot does not modify the source application's
runtime, routes, or dependencies.

## License

Code and documentation: [MIT](LICENSE), preserving the source project's notice.
Bundled Geist Latin font: [SIL Open Font License 1.1](assets/fonts/OFL.txt).
Chinese glyphs use platform fallbacks; no Chinese font files are bundled.
