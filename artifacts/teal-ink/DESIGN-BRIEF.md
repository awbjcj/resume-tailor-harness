# Reuse this design language

Give this file and the `teal-ink/` directory to the designer or coding agent
working on the destination project.

> Apply Teal & Ink, the design language extracted from Résumé Tailor. First read
> `README.md`, `docs/DESIGN-SYSTEM.md`, and `docs/ADOPTION.md`. Inspect the actual
> destination application's routes, data, interactions, and existing component
> library before changing it. Use the included preview as the visual reference.

## The preferred character

- Teal is the action color; dark ink and cool paper provide structure. Keep
  bright colors sparse and meaningful. Use the supplied light and dark values.
- Use Geist for interface text, compact 15px body copy, restrained headings,
  tabular numbers, 4px spacing rhythm, and an 8px base radius. Chinese text must
  have a readable system fallback and enough line height.
- Use shallow two-part shadows, thin decorative rules, a faint 72px background
  grid, and solid card surfaces. Avoid applying the grid to every nested card.
- Prefer full-width compact rows with shared columns and wrapping chips when
  item counts differ. Move labels above content when space runs short.
- Use one filled primary action per task area. Outline and ghost actions stay
  secondary. Active navigation has a teal leading indicator and a quiet tint.
- Keep suggestions, supporting evidence, pending approval, and completed work
  visibly distinct. A proposed change must never look applied already.
- Entry screens may use the mint-on-deep-ink gateway preset. The main workspace
  should retain its regular light/dark theme.
- Motion responds immediately: 150–180ms for small changes, 200–240ms for
  overlays, the supplied strong ease-out curves, and no spatial motion when
  reduced motion is requested. Enable hover transforms only on fine pointers.

## Implementation contract

1. Reuse the destination's accessible interaction primitives. Adopt tokens
   before replacing component behavior. Keep routing, data fetching, business
   rules, billing, and human approval boundaries intact.
2. Read colors from semantic tokens and component details from component
   tokens. Keep raw values in the primitive layer. Rebrand through the token
   JSON and theme boundary overrides, then regenerate the CSS.
3. Scope the CSS with `.ti-root`; use an explicit `data-ti-theme` boundary when
   changing a section's theme. Namespaced variables/classes make incremental
   adoption possible. Do not import `styles/preview.css` into the product.
4. Provide actual loading, empty, error, disabled, selected, and success states.
   Keep a visible label with every field. Pair status color with text or an icon.
5. For dialogs, preserve focus management, Escape, an accessible name, and focus
   return. Use a native modal dialog or the destination's complete dialog
   primitive. A styled container is insufficient.
6. Keep all product copy in the host's localization system. Check English and
   Simplified Chinese, long names, 200% text, narrow widths, both themes,
   keyboard operation, coarse-pointer targets, and reduced motion.
7. Validate after customization. Check readable foreground/background pairs
   and visible form/focus boundaries; chart fills and decorative dividers are
   not substitutes for accessible text or control indicators.

## Handoff

Deliver working compositions, the token overrides, and evidence of the checks
you actually ran. Record intentional deviations and version the destination's
fork. Do not claim a complete accessibility audit from automated checks alone.
