# Resume Agent diagram style

This project-local style records the user's choice to match the existing app.
It does not replace the installed plugin's shared style or create a home profile.
Source: [`web/src/index.css`](../../web/src/index.css), light-theme tokens.

| Semantic role | Value | Source |
| --- | --- | --- |
| paper | `#f6f8fb` | `--background` |
| paper-2 / store | `#eef4f7` | `--secondary` |
| node fill | `#ffffff` | `--card` |
| ink / ink-strong | `#182026` | `--foreground` |
| muted / soft | `#65717c` | `--muted-foreground` |
| accent | `#08708a` | `--primary` |
| accent-tint | `#e6f7fa` | `--accent` |
| link | `#3867d6` | `--info` |
| rule / rule-solid | `#cbd2d9` | Opaque border adapted for exported images |

The HTML uses Geist 400/600 for titles and node names. This is the same family
as the app's locally bundled `Geist Variable`, loaded here from Google Fonts.
Geist Mono 400 is the diagram skill's technical-label fallback; the app has no
separate technical font. Chinese labels use Microsoft YaHei or PingFang SC when
Geist lacks glyphs. SVG exports omit remote fonts; local font substitution is
expected. These exports do not claim pixel-identical typography on every host.

All new views use the `doc-wide` canvas, 1280 × 720, standard diagram type ramp,
orthogonal connectors, at most two focal nodes, and a bottom legend. HTML retains
a local horizontal scroller at narrow widths. Static SVG images scale with the
README; open the linked HTML for full-size reading.

Only the light presentation is published. The architecture and agent workflow
are separate views to stay within the nine-node complexity budget. Optional
integrations, detailed retry states, and individual skills remain in prose and
the agent-role table. Diagram captions state the omitted relationships.
