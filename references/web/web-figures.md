# Web figures

A figure is a **drawing-DSL product**, not an SVG drawn by hand. The page names a
fixture; `scripts/build_web.py` compiles it, validates it, renders it with the
shared SVG renderer, and inlines the result with its provenance. A build error in
the DSL stops the page.

## 1. Host contract

| Item | Value | Source |
|---|---|---|
| Stage width | 240–960 units, a multiple of 4, chosen by the host band | `drawing/stage.py` |
| Canvas height | 400–800 units by family (graph 500–800, chart 400–720, notation 480–800) | `canvas_contract.py` |
| Plate shape | 0.45–1.60 tall per unit wide | `web_contracts.py` |
| Smallest tier | at least 7px in the band the plate is delivered in | `web_contracts.py` |
| Architecture nodes | at most 9 | `drawing-dsl.md:190` |
| Node tiers (architecture) | 144×64 / 176×72 / 224×80, scaled by the stage | `drawing/grammar/architecture.py:76` |
| Focal nodes | at most 2 | `drawing-architecture.md:8` |
| Colour variables per figure | at most 4 | `web_contracts.py` |
| Metadata | `<title>`, `<desc>`, stable id, reading order | DSL renderer |
| Provenance | `data-folio-drawing`, `data-folio-sha`, `data-kind`, `data-folio-plate`, optional `data-composition`, `data-axis` | builder |

The page never chooses coordinates, sizes or colours. The theme reaches the
diagram through the document scheme: `web_figures.drawing_theme_for()` registers
`doc-<theme>` from `folio_theme_for()`, so a forest or slate page draws a forest
or slate diagram.

### The stage is the host's, not the author's

A drawing's type scale is 7 / 9 / 12 units and does not shrink. Its chrome —
padding, gaps, gutters, node boxes — does. So on a narrower *stage*, the same
type occupies a larger share of the plate and arrives larger in the column,
while the drawing keeps the proportions it was authored at. `web_figures.
compose_for_band()` picks the **largest** stage that still clears the 7px floor
and the plate-shape band, which is the smallest change a band requires.

A stage other than 960 is refused for a family that has not earned it:
`drawing/stage.py` lists the families whose geometry actually scales, and until
a family is on that list, "compose for a 350px band" is not a number it can be
given. Today the list holds `architecture`, `state-machine` and `swimlane`.

### One plate per class, or one plate

The composition depends on the band, so one SVG cannot serve a phone and a
desktop. A figure therefore carries one inline plate per *class*, and the
stylesheet shows the one that matches the viewport. A hidden plate is out of
layout and out of the accessible tree, so exactly one drawing is ever rendered
for the reader.

| Class | Viewports | Design band | Shows |
|---|---|---|---|
| narrow | 375–480 | 335 | the phone composition |
| compact | 481–588 | 433 | the small-tablet composition |
| medium | 589–768 | 541 | the large-tablet composition |
| wide | 769 + | 660 (760 at the 1280 step) | the desktop composition |

The design band is the band at the class's *narrowest* viewport, because the
floor binds there. The classes are cut where the band grows by a quarter, so no
reader gets type twice the size another reader gets; the tablet range splits at
the geometric mean of its bands, which is why the page has four figure classes
and three typesetting classes.

A class that cannot be composed has two outcomes, and the difference is the
contract. A family outside `STAGE_AWARE` composes on the authored stage by
design; its single plate (`data-folio-plate="all"`, `data-folio-single="true"`)
is the delivery, the manifest says `single`, and V-FIG-12 reports the size the
reader gets as REVIEW. A stage-aware family that fails to compose for a class
is a defect: the builder records the class in `uncomposed` and falls back to
the authored plate, which is not the band it was measured for. The fit verdict
in `web_plan.fit_verdict` fails that fallback (W-FIG-11), and `web_plan --gate`
exits nonzero. The work that closes such a gap is an arrangement that fits the
band, or adding the family to `STAGE_AWARE`; never lowering the floor.

### What a narrower plate keeps

The type scale does not shrink, so a narrower box holds fewer words. The
descriptor under a node title therefore has three outcomes, decided once for
the whole plate: it fits on one line; it wraps to two lines, and the box is
made tall enough for them (`METADATA_TWO_LINE_HEIGHT`); or it cannot fit in two
lines at all, and the plate drops descriptors from **every** node. Dropping it
for one node alone would read as a rendering fault, so a plate is never
half-labelled.

The outcome follows the class, not the figure: at the design bands the narrow
plate carries titles only, and compact and wider carry the descriptors. A box
never reserves height for a line its plate does not draw, and the authored 960
stage keeps the per-node rule it has always had, so published artefacts do not
move.

The stage search does not assume that a stage which compiles is surrounded by
stages that compile. Less room means more wrapping, and a composition that
fails to resolve at 464 units can resolve at 372. When a candidate is refused,
the search bisects toward the 240-unit floor instead of ending there; the
verdict stays deterministic because the walk and the bisection are fixed.

A legend is type too, and it is placed by measured advance, not by a fixed
width per character. When its items do not fit one row beside the title, they
flow across the plate and the title takes its own line; the box is never wider
than the plate and never overlaps a node.

### Boundaries, routes and connector labels

A group boundary is geometry, and two passes need the same rectangle: the render
pass draws it, and the layout pass has to keep other type off it. It is computed
once, in `layout/regions.py`, and both callers use that. Before it was shared, a
connector label could be placed where a border was drawn afterwards, and a
dashed rule ran through the word.

Three rules follow from that, all of them statements about type:

- A connector crosses a boundary; it never runs along one. When a route's middle
  leg lands on the boundary's own edge, the leg steps outside by one
  edge-to-edge gap, so the border stays dashed instead of reading as solid for
  the length of the crossing.
- The strip inside a boundary's top padding belongs to the boundary's own name.
  Connector labels treat it as occupied. If the name still finds no free slot
  along that line, the boundary keeps its shape and loses its name — a plate
  never sets two labels on top of each other.
- A connector label is an annotation on one path, not a field every path
  carries. It prints only when it can sit beside its own line, within
  `LABEL_REACH` (twice the label's height); otherwise that label alone is
  dropped. Naming one transition and leaving another unnamed is how diagrams are
  read, so this is per label — unlike a node descriptor or a band header, where
  one missing instance would read as a fault.
- The room for one is reserved before anything is placed. A pair of nodes with
  a labelled connector between them gets a gap of at least the label's box plus
  the clearance the placer keeps from each node; a row that cannot afford it
  keeps its ordinary gap. A row is never split to make room for a label,
  because splitting reshapes the plate to save one word. Before the gap was
  reserved, `dispatch` was dropped from every plate: the gap was 48 units and
  the word's box is 48, so with 4 units of air on either side it had nowhere to
  sit.

The floors that make room for that type are derived, not tuned:
`MIN_GROUP_PAD_TOP` (20 units) holds the region name in the boundary's padding,
and `MIN_LAYER_GAP` (44 units) holds a connector label, the air around it, and
that padding. Reserving room is not a guarantee of a place: a plate that grew
its rows further to fit every label would leave the aspect band it has to keep,
so the label placer still decides, per line, and a composed plate may print
fewer labels than the authored one.

### The canvas height follows the stage

Width is not the only axis the stage owns. A plate inherits the height the
drawing was authored at — 540 units for a graph — and a legend pinned to the
bottom edge turns an inherited height the content no longer fills into a hole
between the last row and the legend. A bounding-box coverage number cannot see
that hole; the page can.

So a composed plate is also fitted vertically: the authored height is the
ceiling, the shortest canvas that still compiles without an overlap, a node
outside it or a legend outside it is the floor, and the canvas keeps
`CANVAS_SLACK` units between the last row and the legend. The height band's
floor is layout math measured in stage units, so it scales with the stage
(`CanvasBand.minimum_at`); the ceiling does not, because a canvas can always
be shorter than the authored one but never taller than the family allows.

Fitting the canvas is what lets a seven-node drawing compose for the narrow
class at all. At the 335px band the framing width forces a 336-unit stage, and
at the authored height that plate arrives 1.6 times as tall as it is wide — out
of the page's shape band. On the canvas it actually needs it arrives at 1.36.

### The hole inside the plate

Coverage is the ink's bounding box over the plate, so it cannot see a hole the
drawing contains: two rows at the top and one at the bottom fill the box and
still leave a band of nothing between them. The manifest therefore also records
`empty_band_units` — the tallest horizontal band inside the content that
nothing crosses. Every drawn thing is an occupied interval on the vertical
axis: nodes, region frames, routes, labels, primitives and the legend. The
title is not content, so the band above the first row is the page's, not the
plate's.

The limit is `FIGURE_FIT["empty_band_max"]`, derived from the type: a node
title is 12 units and its line box is 1.25× that, so six lines is 90 units. A
gap taller than six lines of a node's own title is no longer row spacing. On
the plates the page serves the largest real band is 40 units (the strip above a
bottom-pinned legend); the 108-unit hole this rule exists to catch sits well
above the limit. `web_plan.fit_verdict` reports it with the other plate
obligations, so W-FIG-11 fails on it.

### The figure title obeys the page's heading scale

A figure title is a page heading in all but name: it has to read below H2 and
above H3, in both languages. A plate is shown across a whole class, so the
binding number is its delivery at the class's *widest* band, not at the band it
was composed for. The composer therefore picks the largest tier whose widest
delivery stays under `title_h2_ratio` × H2, from 24 down to 14 units in steps
of two.

The tier is a compile-time host input (`title_units`), applied to
`TextRole.DIAGRAM_TITLE` only, and the plate is recompiled at the chosen tier —
the title's own width is part of the ink the frame is cropped to, so a smaller
title can move the frame. The manifest records `title_units` and `title_px`, and
`fit_verdict` checks the pair against H3 and the H2 share, with a one-pixel
tolerance at the floor because the tier ladder moves the delivered size by
about a pixel per step. The standalone artifact keeps its authored 24 units;
only a host that declares a page scale asks for another size.

### Delivered type size

`figures.manifest.json` records, per plate, the stage it was composed on, the
framed viewBox, every drawn tier (`text_sizes`) and the delivered size at its
band (`min_font_px`). `scripts/web_plan.py` recomputes the same numbers for
every reviewed width and `web_verify.py` checks them against the browser.
W-FIG-10 prints them on every check.

The floor is compared with `delivered_tolerance_px` (0.05px), which is smaller
than one stage step at the narrowest band (0.08px). A stage is a multiple of
four units, so a composition can land a hundredth of a pixel under the target
with no stage between it and the one that clears it; refusing it there would
trade a 7.0px plate for a 2.8px single plate over rounding noise.

Enlarging the plate to the drawing's own width was tried and rejected: it moved
the type from 4.8 to 7.2px, but it enlarged the drawing's empty margin by the
same factor, so the page gained a hole and not a legible figure. The floor is
met by composing on a smaller stage and by framing to the ink, not by widening
the plate.

## 2. Composition and kind are different words

The engine has three composition patterns and twenty-three diagram kinds. The
spec uses each where it belongs.

| Word | Values | Where |
|---|---|---|
| `composition` | `layered`, `pipeline`, `hub` | plan figures (architecture layouts) |
| `kind` | architecture, flowchart, bar-chart, … (23) | every figure |

`architecture` maps its layout to a composition: `horizontal-layers` → layered,
`vertical-stack` → pipeline, `hub-and-spoke` → hub. The composition and the
reading axis travel with the figure as `data-composition` / `data-axis` and in
the manifest, and W-FIG-01 compares them with the compiled artefact. They are
not printed under the plate: the caption says what the figure shows, and the
provenance stays machine-readable where a reader will not trip over it. A figure may override the derived composition in `series.json` when the
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
| W-FIG-01 | Every figure declares `data-kind` from the 23 kinds; a plan figure also declares `data-composition` from the three patterns; the attributes and the caption agree with the manifest. |
| W-FIG-03 | The inline SVG carries `<title>` and `<desc>`. |
| W-FIG-05 | A module has at least three figures. |
| W-FIG-06 | Every chapter carries a block component (figure, table, KPI row, phase strip, card grid or insight). |
| W-FIG-07 | Provenance: `data-folio-drawing` + `data-folio-sha` match the manifest entry, and the inline SVG hash matches the compiled artefact. |
| W-FIG-08 | At least one worked-example figure (`data-example="true"`). |
| W-FIG-09 | Architecture figures use only the three node tiers. |
| W-FIG-10 | The manifest records every text tier the scene draws, per plate, and the rule reports the size that plate's band delivers for each. Missing tiers fail the rule. |
| W-FIG-11 | Every plate is framed to its ink: coverage ≥ 75% and the framing margin ≤ 4%. |
| W-FIG-12 | The smallest tier clears 7px in the band each plate is composed for. A one-stage family is reported instead, with the size the reader gets. |
| W-GEO-01 | No ERROR diagnostics in the manifest, and the host checks pass (inline SVG, composed stage 240–960, plate shape, title/desc, one plate per class or one single plate, provenance). |

## 5. Figure density

A chapter explains with a block; a mechanism chapter explains with a figure. The
worked example belongs where the mechanism is described, not in an appendix.

## 6. Adding a figure

1. Write the fixture under `figures/` (JSON, `kind` + nodes/edges).
2. Declare it in `series.json` under `figures[]` with `id`, `fixture`, `caption`.
3. Put `<!--FOLIO:FIGURE:id-->` where it belongs in the fragment.
4. Build. A DSL ERROR names the fixture and the code; fix the fixture, not the page.
