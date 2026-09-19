# Architecture diagrams

The main [README](../../README.md#system-architecture) and its
[Chinese edition](../../README.zh-CN.md#系统架构) share two static architecture
images. They use C4 context and container levels with a manually arranged layout.

| View | Editable presentation | README image | Semantic model |
| --- | --- | --- | --- |
| System context | [HTML](system-context.html) | [SVG](system-context.svg) | [Mermaid C4](system-context.mmd) |
| Containers | [HTML](system-architecture.html) | [SVG](system-architecture.svg) | [Mermaid C4](system-architecture.mmd) |

## Scope and reading conventions

The context view covers the main application workflow. Optional H-1B research,
web search, identity providers, transactional email and subscription gateways
are not expanded. The container view groups external systems into one node;
GitHub and the other context relationships belong to that group too.

The browser app and the Python API are separate runtime containers even when
Docker ships their assets in one image. Background runs are thread pools within
the API process. Services, agents, fact-lock gates, and rendering are internal
code, not separate services. The standalone CLI embeds that code; its external
integration and file-access edges are omitted to avoid duplicated wiring.

The dashed grouping in the rendered container view associates the API with the
active workspace; it does not claim a deployment or network isolation boundary.
Hosted users have separate workspace databases and files, with platform data in
the system database. Local mode uses the default workspace. Arrows show the
initiator of an interaction; responses are implicit except for the separate SSE
event stream.

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

## Editing

Edit the HTML's inline SVG for layout, and update the corresponding `.mmd` when
the architecture changes. The Mermaid files capture nodes and relationships;
their automatic layout is not the source of the published illustration.

To update a README image, extract the first `<svg>...</svg>` block from its HTML
and prepend `<?xml version="1.0" encoding="UTF-8"?>`. The SVG is self-contained:
no scripts, remote font imports, or external images. HTML loads the existing
Instrument Serif / Geist typography; SVG image viewers use the declared local
fallbacks (Georgia / Segoe UI / Consolas) when those fonts are unavailable.

Before publishing, check both SVGs as images at README width, verify labels and
connectors do not overlap, and confirm each HTML diagram matches its SVG export.
The illustrations retain the existing light paper, slate and orange palette.
