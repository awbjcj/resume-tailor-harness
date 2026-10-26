# Architecture diagrams

The main [README](../../README.md#system-architecture) and its
[Chinese edition](../../README.zh-CN.md#系统架构) use localized system context,
runtime architecture, and agent review diagrams. The first two start from C4
context/container concepts; the runtime view also expands internal services
inside one Python process. These are manually arranged layouts, not automatic
Mermaid renders. The [architecture blueprint](../../Project_Architecture_Blueprint.md)
documents the code boundaries in more detail.

| View | Editable presentation | README image | Semantic model |
| --- | --- | --- | --- |
| System context | [HTML](system-context.html) | [SVG](system-context.svg) | [Mermaid C4](system-context.mmd) |
| Containers | [HTML](system-architecture.html) | [SVG](system-architecture.svg) | [Mermaid C4](system-architecture.mmd) |
| Agent review | [HTML](agent-workflow.html) | [SVG](agent-workflow.svg) | [Mermaid flow](agent-workflow.mmd) |

Chinese variants: [context](system-context.zh-CN.html) / [SVG](system-context.zh-CN.svg),
[runtime](system-architecture.zh-CN.html) / [SVG](system-architecture.zh-CN.svg),
and [agent review](agent-workflow.zh-CN.html) / [SVG](agent-workflow.zh-CN.svg).

## Scope and reading conventions

The context view covers the main application workflow. Optional H-1B research,
web search, identity providers, transactional email and subscription gateways
are not expanded. The container view groups external systems into one node;
GitHub and the other context relationships belong to that group too.

External agents and SDK clients now appear explicitly. Application context reads
do not submit forms. The stop-before-submit rule is a handoff instruction for
the external browser agent, not a server-enforced browser permission. The client
box groups browser and SDK entry points rather than claiming they are the same
runtime. The standalone CLI still embeds the use-case services.

The browser app and the Python API are separate runtime containers even when
Docker ships their assets in one image. Background runs are thread pools within
the API process. Services, agents, fact-lock gates, and rendering are internal
code, not separate services. The standalone CLI embeds that code; its external
integration and file-access edges are omitted to avoid duplicated wiring.

The shaded grouping in the runtime view contains API and internal service code
in one Python process; it does not claim a network isolation boundary.
Hosted users have separate workspace databases and files, with platform data in
the system database. Local mode uses the default workspace. Arrows show the
initiator of an interaction. The rendered overview omits responses and the
API-to-browser SSE return path; the semantic model records that stream.

The existing [lifecycle](resume-lifecycle.html) remains a workflow view, not a
third C4 level. Detailed gate behavior stays in the README's harness section.

## Code behind the views

| Architectural claim | Source |
| --- | --- |
| API entry point and built SPA serving | [`api/app.py`](../../src/resume_tailor_harness/api/app.py) |
| CLI directly invokes shared services | [`cli.py`](../../src/resume_tailor_harness/cli.py), [`services/tailoring.py`](../../src/resume_tailor_harness/services/tailoring.py) |
| In-process background workers | [`api/runs/manager.py`](../../src/resume_tailor_harness/api/runs/manager.py) |
| Workspace paths and scoped SQLite | [`tenancy/workspace.py`](../../src/resume_tailor_harness/tenancy/workspace.py) |
| Separate platform database | [`tenancy/system_db.py`](../../src/resume_tailor_harness/tenancy/system_db.py) |
| Model routing and spend policy | [`llm_runner.py`](../../src/resume_tailor_harness/llm_runner.py), [`tenancy/spend.py`](../../src/resume_tailor_harness/tenancy/spend.py) |
| Validated outbound fetches | [`security/outbound.py`](../../src/resume_tailor_harness/security/outbound.py) |
| Packaged frontend and API | [`Dockerfile`](../../Dockerfile) |
| Application context, scoped answers, and revision conflicts | [`services/agent_applications.py`](../../src/resume_tailor_harness/services/agent_applications.py) |
| Screening answers and saved preferences | [`services/application_prompt.py`](../../src/resume_tailor_harness/services/application_prompt.py) |
| Verified skill identities | [`career_skills/registry.py`](../../src/resume_tailor_harness/career_skills/registry.py), [`skills-lock.json`](../../skills-lock.json) |
| Deterministic checks and blocking fact review | [`tailor/workflow.py`](../../src/resume_tailor_harness/tailor/workflow.py), [`tailor/verdict.py`](../../src/resume_tailor_harness/tailor/verdict.py) |
| External-draft acceptance and context revision | [`services/external_tailoring.py`](../../src/resume_tailor_harness/services/external_tailoring.py) |
| Bounded taxonomy recovery and reversible cleanup | [`services/match_gap.py`](../../src/resume_tailor_harness/services/match_gap.py), [`taxonomy/non_skills.py`](../../src/resume_tailor_harness/taxonomy/non_skills.py) |

## Editing

Edit [`generate.py`](generate.py) for shared geometry and bilingual labels, run
`python docs/diagrams/generate.py` from the root, and update the corresponding
`.mmd` when relationships change. Each generated HTML is the presentation source
for its exported SVG. The Mermaid files capture semantic relationships; their
automatic layout is not the source of the published illustration.

Use Diagram Design's installed `scripts/self_check.py <file.html>` and
`scripts/export_svg.py <file.html> <file.svg> --system-fonts` for each new view.
The SVG is self-contained: no scripts, remote font imports, or external images.
HTML uses the app's Geist family, with a separate technical-label fallback.
See the [local style receipt](style-guide.md) for palette sources and font
substitution. The older lifecycle illustration keeps its existing presentation.

Before publishing, check both SVGs as images at README width, verify labels and
connectors do not overlap, and confirm each HTML diagram matches its SVG export.
The new illustrations use the app's light blue-gray and teal palette. Keep
English/Chinese HTML and SVG synchronized, verify arrow routing and text bounds,
and check a narrow viewport's local scroller before publishing.
