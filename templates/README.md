# Resume layouts

Eight bundled Typst layouts accept the same fact-locked `ResumeContent` JSON.
Choose one in **Settings → Rendering**; previews use fictional sample data.
Every layout is single-column, uses selectable text, keeps contact information
in the document body, and supports every resume section. No icons, photographs,
skill meters, remote packages, or font downloads are required.

## Catalog and design research

The GitHub repositories and Typst Universe pages below were reviewed on
2026-10-29. These are locally implemented layouts inspired by their design
patterns, **not the upstream packages or exact copies of their output**. Our
shared `resume-base.typ` adapts those patterns to this application's JSON,
provenance-safe highlighting, optional sections, and page-fitting contract.
No upstream template source is vendored.

| ID | Purpose and treatment | Design reference |
| --- | --- | --- |
| `classic` | General applications; centered serif name, ruled capitals | [basic-resume / Jake's Resume](https://github.com/stuxf/basic-typst-resume-template), [Universe](https://typst.app/universe/package/basic-resume) |
| `modern` | Product, business, technology; left header, sans-serif, blue section rules | [Modern CV](https://github.com/ptsouchlos/modern-cv) (MIT), [Universe](https://typst.app/universe/package/modern-cv) |
| `technical` | Engineering and project work; monochrome sans-serif, work-first hierarchy | [imprecv](https://github.com/jskherman/imprecv) (Apache-2.0), [Universe](https://typst.app/universe/package/imprecv) |
| `executive` | Senior professionals; serif typography, navy hierarchy, more section space | [Brilliant CV](https://github.com/yunanwg/brilliant-CV) (Apache-2.0), [Universe](https://typst.app/universe/package/brilliant-cv) |
| `graduate` | Students and internships; education first, centered section headings | [readable-classic](https://typst.app/universe/package/readable-classic) (MIT library / MIT-0 examples) |
| `academic` | Research applications; education/publications first, quiet serif headings | [Brilliant CV's modular research sections](https://typst.app/universe/package/brilliant-cv) |
| `minimal` | Simple professional presentation; left header, monochrome, no rules | [kiresume](https://typst.app/universe/package/kiresume) (Unlicense) |
| `compact` | Substantial work/project evidence in less space; tighter serif hierarchy | [ttq-classic-resume](https://typst.app/universe/package/ttq-classic-resume) (MIT) |

Serif families ship with Typst. The four static **Source Sans 3** faces in
`fonts/` are bundled from [Adobe's release branch](https://github.com/adobe-fonts/source-sans/tree/release/OTF)
under the [SIL Open Font License](fonts/LICENSE.md), with the original license
and copyright retained. Rendering does not depend on fonts installed on the
host or runtime downloads. Essential information stays black; accent color
is decorative. Explicit `section_order` takes precedence over each layout's
default order; omitted populated sections are appended rather than lost.

## Length and content policy

**Fit resume to one page** also selects the authoring envelope for new native
and external tailoring contexts. Older two-page review budgets are bounded to
three roles, three projects, five combined entries, and about 16 bullets:
2–4 per role and 1–3 per project, clamped to actual source supply. Lower saved
caps are respected. A project slot is reserved when work and project evidence
both exist. One-page native drafts omit the summary before review; no work or
project content is cut by this normalization. Writers receive a 400–550 word
guide and prioritize actual work over repeated descriptions or secondary details.

Turning the option off selects detailed drafting and an export limit of two
pages, using the saved review roster's larger budget. Short content can remain
one page; no filler or extra page is manufactured. A small second-page tail
triggers one optional balance probe at an entry or section boundary, retained
only when it improves the second page without adding a third.

Bundled pages are US Letter with 0.6-inch horizontal and 0.55-inch vertical
margins, 10–10.5pt body text, 12pt headings, and a 20pt name. Fitting uses a
natural layout, a compact bound, and at most three binary probes. It reuses a
compiler within that render and works in memory. Unlike the old linear zoom
loop, fitting never shrinks bundled body text below 10pt or silently accepts
overflow. Headings stick to following content; bullets stay together while
long sections can continue to the next page.

An impossible fit raises `PageFitError` (HTTP 422 `resume_page_overflow`) with
shortening/two-page guidance. No new PDF is published and any previous artifact
is preserved. Rendering never truncates or deletes approved resume content.
Direct Python calls to `render_pdf(..., fit_pages=None)` remain available for an
unrestricted full CV. Uploaded templates retain the existing `data` and `zoom`
inputs; `density` and `break_before` are optional enhancements. Their own font
rules remain the template author's responsibility.

The formatting/content policy applies the supplied `resume-formatter` and
`resume-section-builder` playbooks: readable type, standard section names,
consistent hierarchy, optional summaries, and work/project evidence first.
Fact-lock gates continue to review every resulting native draft.
