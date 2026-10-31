# Web performance budget

`npm run build` runs `perf:check` against Vite's production manifest. It sums
gzip bytes for every transitive static JavaScript import, counting each asset
once. Route totals include the entry, authenticated shell, and selected route.
CSS, fonts, API payloads, and the separately loaded Chinese catalog are excluded.
These are download-size measurements, not browser latency or Core Web Vitals.

| Surface | Target / regression ceiling | Local measurement, 2026-10-30 |
| --- | ---: | ---: |
| Initial static JavaScript | 200 KB target; 265 KB ceiling | 263.01 KB gzip, down from 333.39 KB |
| Cold Dashboard JavaScript | 360 KB ceiling | 354.57 KB gzip, previously 355.01 KB |
| Cold Pipeline JavaScript | 625 KB ceiling | 618.08 KB gzip, previously 617.03 KB |
| Largest deferred JavaScript chunk | 120 KB ceiling | chart dependencies, ~104 KB gzip |
| Board page response | 150 KB | enforced by pipeline payload tests |

KB means 1,000 bytes. The 200 KB startup target remains **unmet**. The older
131.72 KB claim counted only two named chunks and omitted transitive imports.
The ceilings prevent regression from this measured baseline; they are not a
claim that the target has been reached. The script prints exact byte counts.

Public routes avoid the authenticated shell. Manual entry, URL import, file
import, and email composition download their form bodies only on first use.
Their triggers remain mounted and loaded form state survives closing. English
and Chinese loading/error messages are available immediately. Failed module
downloads offer an explicit reload because browsers can cache failed imports;
reloads are never automatic and can discard other unsaved page input.

The build groups only modules already in the initial static graph. This avoids
extra compression overhead from small shared chunks without pulling optional
forms into startup. Cold Dashboard bytes are effectively unchanged; Pipeline
is 0.2% larger. The gain is in the initial/public graph and on-demand forms,
not a claimed reduction in every authenticated route's download size.

Further work toward 200 KB should profile the synchronous translation catalog
and shared UI imports. Preserve translated first render and language switching;
moving bytes to an unconditional asynchronous download is not a startup win.
Cold-route totals deliberately expose costs that entry-only measurements hide.
