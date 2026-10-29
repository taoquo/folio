# Web figures

A figure is a **drawing-DSL product**, not an SVG drawn by hand. The page names a
fixture; `scripts/build_web.py` compiles it, validates it, renders it with the
shared SVG renderer, and inlines the result with its provenance. A build error in
the DSL stops the page.

## 1. Host contract

| Item | Value | Source |
|---|---|---|
| Stage width | 960 units | `drawing/canvas_contract.py` |
| Canvas height | 400–800 units by family (graph 500–800, chart 400–720, notation 480–800) | `canvas_contract.py` |
| Rendered height | 275–550 px at the 660px slot, 315–635 px at the 760px wide step | `web_contracts.py` |
| Architecture nodes | at most 9 | `drawing-dsl.md:171` |
| Node tiers (architecture) | 144×64 / 176×72 / 224×80 | `drawing/grammar/architecture.py:25` |
| Focal nodes | at most 2 | `drawing-dsl.md:30` |
| Colour variables per figure | at most 4 | `web_contracts.py` |
| Metadata | `<title>`, `<desc>`, stable id, reading order | DSL renderer |
| Provenance | `data-folio-drawing`, `data-folio-sha`, `data-kind`, optional `data-composition`, `data-axis` | builder |

The page never chooses coordinates, sizes or colours. The theme reaches the
diagram through the document scheme: `web_figures.drawing_theme_for()` registers
`doc-<theme>` from `folio_theme_for()`, so a forest or slate page draws a forest
or slate diagram.

## 2. Composition and kind are different words

The engine has three composition patterns and twenty-three diagram kinds. The
spec uses each where it belongs.

| Word | Values | Where |
|---|---|---|
| `composition` | `layered`, `pipeline`, `hub` | plan figures (architecture layouts) |
| `kind` | architecture, flowchart, bar-chart, … (23) | every figure |

`architecture` maps its layout to a composition: `horizontal-layers` → layered,
`vertical-stack` → pipeline, `hub-and-spoke` → hub. The reading axis in the
caption is not a second label: `web_figures` copies it from the composition the
planner produced, so a caption cannot claim a direction the figure does not read
in. A figure may override the derived composition in `series.json` when the
layout is chosen for geometry and the composition names the meaning (a fan-in
drawn on horizontal layers is still a hub); the override never moves the axis. A
data figure such as a bar chart declares only its kind.

`explain` is not an engine composition. The requirement is expressed as a
**worked example**: a figure carrying `data-example="true"` that shows concrete
values (shapes, counts, dimensions), placed in the mechanism chapter.

## 3. What is validated, and by whom

Geometry is not re-implemented on the page. The compiler's scene validation runs
first and its ERROR diagnostics fail the build.

| Target-doc audit | Where it lives now |
|---|---|
| Endpoint anchoring | DG103 / DG104 / DG129 |
| Orthogonal routing, no diagonals | DG113 |
| Connectors do not cross nodes | DG109 |
| Arrowhead shape | DG110 |
| Labels vs nodes / connectors / labels | DG133 / DG134 / DG135 |
| Fan-out spacing | DG115 / DG116 |
| Legend bounds and text | DG130 / DG131 |
| Legend vs node / label / region | **DG141** |
| Shape truth (parallelogram, right angle) | **DG140** |
| Arrow entry at least 24 from a corner | **DG142** (advisory) |
| Tip-to-edge gap, hop gaps | not applicable: the DSL anchors endpoints by construction |

`ERROR` stops the build. `WARNING` and `TASTE` are recorded in
`figures.manifest.json`; a strict build (`--strict-figures`) turns them into
failures.

## 4. Rules

| Rule | Statement |
|---|---|
| W-FIG-01 | Every figure declares `data-kind` from the 23 kinds; a plan figure also declares `data-composition` from the three patterns; the caption agrees. |
| W-FIG-03 | The inline SVG carries `<title>` and `<desc>`. |
| W-FIG-05 | A module has at least three figures. |
| W-FIG-06 | Every chapter carries a block component (figure, table, KPI row, phase strip, card grid or insight). |
| W-FIG-07 | Provenance: `data-folio-drawing` + `data-folio-sha` match the manifest entry, and the inline SVG hash matches the compiled artefact. |
| W-FIG-08 | At least one worked-example figure (`data-example="true"`). |
| W-FIG-09 | Architecture figures use only the three node tiers. |
| W-GEO-01 | No ERROR diagnostics in the manifest, and the host checks pass (inline SVG, 960 stage, height band, title/desc, provenance). |

## 5. Figure density

A chapter explains with a block; a mechanism chapter explains with a figure. The
worked example belongs where the mechanism is described, not in an appendix.

## 6. Adding a figure

1. Write the fixture under `figures/` (JSON, `kind` + nodes/edges).
2. Declare it in `series.json` under `figures[]` with `id`, `fixture`, `caption`.
3. Put `<!--FOLIO:FIGURE:id-->` where it belongs in the fragment.
4. Build. A DSL ERROR names the fixture and the code; fix the fixture, not the page.
