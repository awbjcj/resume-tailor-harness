# Resume formatting rules

Reviewed 2026-10-31 against the local resume/CV skills and the template sources
linked in [the catalog](../templates/README.md). These are application rules,
not modifications to installed skills or to the candidate's master profile.

## Local skill review

The local `.agents/skills` collection supplies the following playbooks; the
application-workflow skill lives in `.codex/skills`. Their applicable rules are
combined below rather than injected wholesale into every model prompt.

| Skills reviewed | Rule adopted |
| --- | --- |
| `resume-formatter` | Single column, selectable PDF text, contact in the body, standard headings, readable type and consistent spacing; avoid half-empty pages. |
| `resume-section-builder` | Use relevant supplementary sections and section order appropriate to career stage. |
| `resume-ats-optimizer`, `ats-resume-checker` | Preserve text extraction order; use truthful terms, simple bullets and conventional headings; no keyword stuffing, skill bars or essential images. |
| `resume-tailor`, `resume-customizer` | Concise targeted summary, relevant evidence first, truthful keywords, no invented titles or credentials. |
| `resume-bullet-writer`, `resume-quantifier` | Concrete action, contribution and outcome; normally one or two lines. Numbers require source evidence. |
| `tech-resume-optimizer`, `software-engineer-resume` | Categorized atomic technology names; technical project evidence and visible portfolio/repository links. |
| `academic-cv-builder`, `academic-research-cv` | Education/publications prominent; preserve author order, venue/date/link; optional teaching, grants, presentations, service and honors. |
| `executive-resume-writer`, `executive-leadership-resume` | Short leadership summary, supported scope/outcomes, board/advisory work and recognition. |
| `creative-portfolio-resume` | Link to work and case studies; use restrained typography and color while keeping the PDF readable as text. |
| `portfolio-case-study`, `portfolio-case-study-writer` | Brief project context, actual contribution and timeline on the resume; link to the deeper process, decisions and results instead of inserting a long case study or images. |
| `technical-job-search`, `career-changer-translator` | Translate relevant supported experience into clear target-role language; preserve actual titles, ownership, qualifications and dates. Adjacent skills never become exact qualifications merely through rewording. |
| `project-resume-dossier` | Project claims and metrics require actual evidence; do not promote a project into employment or manufacture ownership. Current per-highlight fact IDs take precedence over older skill descriptions. |
| `resume-version-manager` | Keep the master facts and previously saved artifacts intact; tailored versions select from that source. |
| `resume-harness-job-application` | Inspect and bind the exact reviewed PDF/version; a render is not an employer submission or proof of live ATS acceptance. Application actions are outside this change. |
| Bundled `resume-harness-tailor`, `resume-harness-apply` | Read the live authoring schema, preserve source IDs, and respond to page-fit feedback with a reviewed content revision; the SDK does not rewrite approved content at render time. |

## Resolved rules

1. **Summary:** include a useful 25–40-word summary in either page mode. Preserve
   an explicit connection between the job's main responsibilities and the candidate's
   strongest verified capabilities or accomplishments, explaining why they fit this
   specific position. A generic biography or unsupported "excellent fit" assertion
   does not satisfy this rule. Preserve
   its evidence IDs through initial drafts and revisions, sync and async. Missing
   or unsupported claims must be visible to the existing gates. No filler praise,
   objectives, inferred tenure or invented metrics.
2. **Optional means evidence-dependent:** omit empty sections. Standalone honors
   use `awards`; education honors stay with the degree. Publications preserve
   authors and citation details. Credentials retain issuer/date/ID/link. Portfolio
   records cite project facts and share their budgets; never duplicate a project.
3. **Other source sections:** preserve additional headings and selected entries
   verbatim, with stable IDs, through extraction, merging, review and rendering.
   Teaching, grants, patents, service and advisory work cannot become unreviewed
   free-text escape hatches. Interests must match the source profile.
4. **Content adjustment:** select distinct relevant facts, shorten repetitions and
   prioritize recent relevant work. One-page guide: 400–550 words including summary
   and optional sections. Detailed guide: 650–900 words only with enough evidence.
   Saved bullet/owner limits still apply. Word counts guide writing, not forced
   truncation or padding; the final PDF supplies the layout measurement.
5. **Layout adjustment:** US Letter, 0.6in horizontal/0.55in vertical margins,
   10–12pt body, 12pt headings, 20pt name; adjust leading and bullet/entry/section
   spacing together. Retain hyperlinks, content, ordering and provenance.
6. **Page acceptance:** one page, or two pages with at least 80% of the printable
   height occupied on each. Try compacting a short spill first, then bounded
   expansion. If neither works, request a content revision and preserve existing
   artifacts. Do not disguise a sparse resume with a forced middle page break.
7. **Conflicts:** the user's two-page maximum supersedes longer academic/executive
   guidance; unrestricted Python CV rendering remains available. Fact-lock
   supersedes skill suggestions to estimate numbers or demand a metric in every
   bullet. Single-column readability supersedes competency grids or visual
   portfolio layouts. No universal ATS score or guaranteed parsing is claimed.
8. **Visual review:** native tailoring, external draft submission and requested
   re-review render the actual selected template before scoring. The `concision`
   reviewer (also in the merged advisory panel) receives PNG page images, page
   count, fill measurements and page-fit diagnostics. It checks readability,
   whitespace, clipping, alignment and page breaks, and sends page-specific edits
   into the bounded revision loop. `layout_density` is a persisted preference
   from -1 (roomier, up to 12pt) to 1 (compact, 10pt); export uses the same fitting
   rules and may adjust the preference. Content changes re-enter all fact gates.
   `layout-fit` blocks acceptance when the renderer cannot satisfy the budget.
   A failed fit gets diagnostic screenshots, never a published draft artifact.
   Only the format reviewer receives images in separate mode; fact-check still
   uses cited facts. A reviewer model with image input support is required;
   provider/adapter failures are surfaced rather than silently claiming visual review.
   Previews stay in memory after temporary PDF cleanup, with at most four images
   of 1600px per edge and a 12MiB byte cap. No preview URLs or cross-tenant cache.

## Validation

Real Typst compilation tests cover all eight layouts, optional text and PDF links,
empty sections, one-page spill compression, two-page fill, 10pt minimum type,
content preservation and atomic failure. Source tests cover stable additional
IDs, merging, source-heading integrity, portfolio evidence and numeric gates.
Both native workflow variants verify that unsupported summaries remain visible
to the gate. UI copy describes the same policy in English and Chinese.
Visual tests exercise real PNG delivery in both panel modes and workflow variants,
fresh screenshots after revision, failure propagation, bounded previews and cleanup,
font preferences, and the independent fact gates. Provider transport is tested with
fakes; these tests do not establish live model vision quality.

The multimodal adapter follows [Agno's image-bytes interface](https://docs.agno.com/models/providers/native/anthropic/usage/image-input-bytes).
Rasterization follows [PDFium's rendering and threading rules](https://pypdfium2.readthedocs.io/en/stable/python_api.html).
