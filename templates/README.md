# Resume layouts

Eight bundled Typst layouts accept the same fact-locked `ResumeContent` JSON.
Choose one in **Settings → Rendering**; previews use fictional sample data.
Every layout is single-column, uses selectable text, keeps contact information
in the document body, and supports every resume section. No icons, photographs,
skill meters, remote packages, or font downloads are required.

## Catalog and design research

The GitHub repositories and Typst Universe pages below were reviewed on
2026-10-29. These are locally implemented layouts inspired by their design
patterns. **They do not use the upstream packages or copy their output exactly.**
The shared `resume-base.typ` adapts those patterns to this application's JSON,
highlights backed by source evidence, optional sections, and page limits.
No upstream template source is included.

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

## Optional sections and source formats

All eight layouts render populated sections and omit empty headings. The summary
is included in both page modes and remains visible to provenance and fact-check.
Explicit `section_order` wins; omitted populated sections are appended once.
`honors` in the order is an alias for the existing `awards` data field.

- **Honors & Awards:** standalone award name, issuer, date and description;
  education-specific honors and activities remain under Education. Graduate and
  Academic place recognition early; Executive follows experience/advisory roles.
- **Publications:** preserve author order, linked title, venue and date, following
  [Brilliant CV's citation-oriented source](https://github.com/yunanwg/brilliant-CV/blob/main/template/profile_en/publications.typ).
  Academic places publications immediately after education.
- **Certifications:** name, issuer, date, credential ID and clickable source link,
  informed by [Brilliant CV's honor entries](https://github.com/yunanwg/brilliant-CV/blob/main/template/profile_en/certificates.typ)
  and [imprecv's structured fields](https://github.com/jskherman/imprecv/blob/main/template/template.yml).
- **Portfolio:** project-backed case studies with actual role, dates, visible work
  and repository links, description, technologies and achievement bullets. This
  follows [Modern CV's project entries](https://github.com/ptsouchlos/modern-cv/blob/main/template/sections/projects.typ).
  It shares the project evidence budget; never duplicate a project in both lists.
- **Other sections:** languages, volunteering and interests are supported.
  `additional_sections` retains source headings and verbatim entries for teaching,
  grants, presentations, patents, memberships, service or board/advisory work.
  Each entry has a stable fact ID. The deterministic gate verifies both its heading
  and content against the source; unsupported entries cannot bypass review.

Source formats were rechecked on 2026-10-31. These remain local adaptations:
no copied package code, remote imports, icons, photographs or layout tables.
Template previews include fictional examples appropriate to their purpose.

## Length and content policy

**Fit resume to one page** sets the drafting limits for native and external
contexts. Larger legacy budgets are capped at three roles, three projects, five
combined evidence owners and about 16 bullets (2–4 per role, 1–3 per project),
depending on the available source evidence. Lower saved caps still apply. Portfolio
work shares the project budget. Include a concise 25–40-word summary with `summary_provenance`,
connecting the job's main requirements to verified capabilities or accomplishments
to explain the candidate's fit for that position. Never silently erase it before
review. Aim for 400–550 words including optional sections. Preserve distinct work
and project evidence; shorten repetition first.

Turning the option off allows one page or two nearly full pages. Writers target
650–900 words only when verified, relevant evidence supports that detail. Expand
selected achievements and relevant optional sections during drafting/revision,
never by adding filler or unsupported facts. The saved length-budget controls
continue to govern content selection and bullet counts.

The format reviewer receives rendered page images and gives page-specific feedback.
Revisions can change `layout_density` from -1 (roomier/up to 12pt) to 1 (compact/10pt),
along with evidence-backed content edits. The export fitter may adjust this preference
to meet the page budget. Each native revision is rendered and reviewed again.

Bundled pages are US Letter with 0.6-inch horizontal and 0.55-inch vertical
margins. The fitter adjusts body text within **10–12pt**, paragraph leading,
bullet spacing, entry spacing and section gaps. Names stay 20pt and headings
12pt. It measures the text span against the printable area on **both** pages;
each must occupy at least **80%** for a two-page export. This is a vertical layout
measure, not an ATS score or a count of ink pixels.

Fitting first tests the natural layout and bounded whitespace/font compression
(at most five probes). In detailed mode, a sparse second page is compacted into
one page if possible; otherwise bounded expansion adds readable type and spacing
(at most six expansion probes). It never merely moves a page break to produce
two short pages. A render uses at most twelve compiler calls, with one compiler
cache scoped to that render. Headings stay with following content and bullets
stay together while long sections can continue onto the next page.

If approved content cannot fit within the readable range, `PageFitError` requests
revision. If neither a concise page nor two sufficiently full pages is possible,
`PageBalanceError` requests verified additions or a shorter draft. Both map to
HTTP 422 `resume_page_overflow`; previous artifacts remain intact. Rendering
never changes, truncates or adds approved resume content.

Direct Python calls with `fit_pages=None` remain available for unrestricted CVs.
Uploaded templates retain their `data` and `zoom` contract and the page-count
limit; automatic expansion and the 80% rule apply to bundled templates only.
Custom template authors remain responsible for their typography and spacing.

See [the local resume-skill review and resolved rules](../docs/resume-formatting-rules.md)
for role-specific rules, conflicts, evidence requirements and validation.
