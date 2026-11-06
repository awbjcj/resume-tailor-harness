# Rendering developer reference

Migrated from the project root `CLAUDE.md` (2026-08-15, CLAUDE.md split) — loads only when working under `src/resume_tailor_harness/render/`.

- **Rendering is template-id based.** The settings contract is `{template,
fitOnePage}`; legacy `template_path` and `output_dir` remain runtime-only CLI
  fields. Bundled templates are anchored in `render/templates.py`; validated
  custom `.typ` uploads live under the tenant `config/templates/` directory.
  Custom stems are path-safe, Typst compilation is root-pinned, and uploads
  replace live templates only after a successful validation compile. Deleting
  an active custom template falls back to `classic`; missing templates never
  silently fall back during rendering.
- A saved version can render with a per-request `templateId`. The version
  records the PDF's template only after publication. A replacement compiles
  before taking the SQLite writer, then checks that the version still exists
  and publishes the PDF and metadata together.

- **Eight bundled layouts share `templates/resume-base.typ`.** Stable ids are
  classic, modern, technical, executive, graduate, academic, minimal, compact.
  Source references and the bundled Source Sans 3 license are in
  `templates/README.md` and `templates/fonts/LICENSE.md`. Compile with the
  bundled font directory; do not require host fonts or remote Typst packages.
  Default body text is 11pt with separate entry/metadata blocks. Compact fitting
  must preserve the shared spacing floors; real PDF glyph-bound tests cover all
  layouts/densities. Bundled catalog previews use the one-page export fitter.
- **Metadata has one presentation policy.** `render/formatting.py` formats a
  deep display copy before compilation, shared by exports and visual review.
  Role and skill-category labels use title case while retaining acronyms and
  mixed-case product names. Known month dates use `Mon YYYY`; full dates retain
  their day and year-only/unknown formats retain their precision. Source names,
  claims, links, skill names, stored content and provenance are never rewritten.
  Categories that converge after formatting merge without losing entries.
- **Export length is validated before publication.** `fit_one_page` selects
  one page or a maximum of two. Bundled fitting uses bounded compression/expansion (at most twelve calls),
  10–12pt body text, and at least 80% printable-height fill on both pages.
  A short spill compacts into one page; insufficient two-page fill raises
  `PageBalanceError` for content revision. Custom templates retain page-count
  validation without bundled expansion. `PageFitError`
  leaves previous artifacts intact and maps to an actionable 422. Rendering
  never cuts approved content. `services/resume_shape.py` aligns authoring
  budgets with this length before any native planning or external context.
- **Visual review uses the export renderer.** `layout_review.py` renders the
  selected tenant template with the same length, density and highlight terms.
  The concision reviewer receives bounded in-memory page PNGs; failed fits
  produce diagnostic previews and a deterministic `layout-fit` failure.
  Temporary PDFs are removed before provider calls. PDFium operations, including
  resource cleanup, must hold the process-wide lock. Async rendering runs off
  the event loop under the batch semaphore. Preview failures must never silently
  become successful visual reviews. The persisted `layout_density` preference
  stays within [-1, 1]; page fitting and the 10pt floor take precedence.
