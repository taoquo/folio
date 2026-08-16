# Drawing DSL V6 Final Audit

Scope: closing audit for the Drawing DSL program. This document records the objective state of the
twenty-three-kind generator catalog against the reference editorial principles, the project's own
quality gates, and a full visual pass over a purpose-built showcase corpus.

Status: complete
Audit date: 2026-08-15, remeasured 2026-08-16 after heatmap and the bounded canvas knob
Predecessor: `archive/drawing-dsl-v5-final-audit.md`

## 1. Reference-principle conformance

The reference project is [diagram-design](https://github.com/cathrynlavery/diagram-design). Folio
adopts its editorial principles, not its HTML templates. Conformance is assessed principle by
principle.

| Reference principle | Folio implementation | State |
|---|---|---|
| Constrained visual vocabulary | Scene primitives limited to rect, line, circle, path, text, group; no ad-hoc SVG in payloads | Met |
| One focal accent per diagram | ADR 0006 theme invariant, enforced by `VQ103` (accent elements <= 2) and `VQ104` (solid brand <= 5% area) | Met |
| Semantic tokens over literal color | Payloads carry roles and importance; theme resolves color at render time | Met |
| Grid discipline | 4-unit grid enforced on every `SceneText` by `DG119` | Met |
| Deletion-first information budget | Per-kind caps on nodes, edges, series, labels; `WARNING` before `ERROR` | Met |
| Anti-slop rules as an executable gate | 5 canvas/taste gates (`VQ101`-`VQ107`) plus 12 geometry gates run on every compile | Met |
| Inline SVG output, document-native | `artifact`, `embed`, and `page-preview` profiles; host embedding verified by digest | Met |
| Editorial type scale and serif hierarchy | Shared Folio theme across all kinds; contrast gated by `VQ106`/`VQ107` | Met |
| Catalog breadth | 23 generator-backed kinds against the reference project's 13 | Exceeded |

Folio additionally enforces properties the reference project leaves to the author: deterministic
layout, fail-closed validation, accessibility reading order (`AX200`-`AX203`), and theme/knob/variant
separation from payload (ADR 0008).

## 2. Showcase visual audit

A dedicated 23-file corpus under `references/fixtures/showcase/` was authored on a single subject
("Orbital Publishing Platform") so that every kind is exercised with realistic content rather than
minimal contract data. All 23 were rendered to PNG and SVG under the `artifact` profile and reviewed
one by one.

| Check | Result |
|---|---|
| Compile diagnostics across 23 showcase fixtures | 0 diagnostics of any level |
| PNG render | 23 rendered, 0 failed |
| SVG render | 23 rendered, 0 failed |
| Manual visual review | 23 / 23 reviewed, 23 / 23 accepted |

### 2.1 Defects found and fixed in this pass

| Defect | Root cause | Fix |
|---|---|---|
| Swimlane edge labels landed on lane borders or outside the canvas | Lane chrome and canvas padding were not label-placement obstacles | Lane borders, lane titles, and stack margins registered as obstacles and passed into `route_graph_edges` |
| Edge labels drifted onto a neighbouring connector | Candidate boxes only moved perpendicular to the segment | Added `ALONG_FRACTIONS` so a label slides along its own segment before changing segment |
| Donut legend read `46% - 46.0%` | Share was appended even when the unit already was a percentage | Share suffix suppressed when `unit` is `%` |
| Sibling connectors crossed in tree and org-chart | Fan-out order was alphabetical by id | Fan-out ordered by the opposite endpoint's coordinate |
| Bar-chart value labels collided with reference lines | Reference line drawn over label text | Knockout rect behind each value label in the canvas fill |
| Tree siblings fanned out from three offset anchors instead of one trunk | Hierarchy reused the generic `route_graph_edges` fan-out | `_tree_bus_scene` rewrites tree connectors as shared-bus `ScenePolyline` primitives; `_primitive_connectors` preserves edge and bend metrics |

### 2.2 Gate evidence

| Check | Result |
|---|---|
| Full regression | `Ran 328 tests` -> `OK (skipped=3)` |
| `build.py --check` | `OK: no violations across 30 templates` |
| `build.py --sync` | `OK: tokens in sync across 30 template(s)` |
| `build.py --verify` | exit 0, zero error lines |
| `diagram-catalog --baseline` | `OK: visual baseline: 23 diagrams passed` then `OK: diagram catalog: 23 types, 23 Drawing DSL, 0 HTML baselines` |

## 3. Canvas utilization measurement

Content-bounds utilization was measured for all 23 showcase renders on the default 960 x 540 canvas.
Every kind clears `VQ101` (>= 0.08) and `VQ102` (no dominant margin), but utilization is not uniform.

Measured with the `VQ101` algorithm itself (`quality.py:_content_boxes` union over the resolved
scene), each kind at the canvas its own generator produces. Values are exact, not estimated.

| Band | Kinds (measured `VQ101` ratio) |
|---|---|
| 0.36 - 0.47 | timeline 0.360, tree 0.375, donut-chart 0.471 |
| 0.49 - 0.62 | state-machine 0.488, uml-class 0.514, flowchart 0.520, venn 0.523, er-diagram 0.541, candlestick 0.542, quadrant 0.545, architecture 0.553, waterfall 0.554, layer-stack 0.574, loop-flywheel 0.581, org-chart 0.581, line-chart 0.593, pyramid 0.613, scatter 0.617, bar-chart 0.620 |
| 0.65 - 0.72 | heatmap 0.654, sequence 0.671, swimlane 0.674, gantt 0.712 |

Three kinds do not use the default canvas: `state-machine` renders 960 x 400, `er-diagram` and
`uml-class` render 960 x 640. No showcase fixture sets `width` or `height`, so every number above is
the shipped default for that kind.

The two lowest values are structural rather than radial: `timeline` is a single horizontal axis and
`tree` is a shallow three-tier hierarchy, and neither can fill a 16:9 rectangle without inflating
marks past the type scale. Authors who want a tighter frame can set `height` explicitly where the
generator permits it; on `timeline`, `height: 400` raises utilization from 0.360 to 0.48 with zero new
diagnostics, and `tree` moves 0.375 -> 0.51 the same way. Changing the shipped default would move
every committed geometry baseline, so the default stays 960 x 540 while `height` is an enforced,
bounded knob on every data chart and notation diagram.

### 3.1 What the `height` knob does and does not do

The knob is bounded and enforced, not universal. Two families accept a checked range and derive
their geometry from the canvas; the remaining kinds pass validation only near their default.

| Family | Accepted canvas | Enforcement |
|---|---|---|
| bar-chart, candlestick, donut-chart, gantt, heatmap, line-chart, scatter, waterfall | width 960, height 400-720 step 4 | `_validate_canvas` in `scripts/drawing/dataviz.py` |
| er-diagram, sequence, uml-class | width 960, height 480-800 step 4 | `_valid_height` in `scripts/drawing/notation.py` |

Out-of-range values fail with `DN000` naming the accepted range, and the JSON contracts in
`references/schemas/types/` carry the same bounds, so schema validation and compilation agree.
Width stays fixed at 960 in both families because every gutter, legend, and label constant is
measured against it.

The knob changes the frame, and only some kinds gain utilization from a shorter frame. Measured with
the same `VQ101` algorithm over the showcase corpus:

| Kind | Measured behaviour | Cause |
|---|---|---|
| timeline | 0.360 at 540, 0.441 at 440, 0.476 at 400 | marks are height-independent, so a shorter frame is a real gain |
| tree | 0.375, 0.460, 0.506 | same, tier spacing is capped |
| donut-chart | 0.471, 0.420, 0.387 | radius is height-derived, so content shrinks with the frame |
| candlestick | 0.542, 0.486, 0.455 | plot band is height-derived, same effect |
| uml-class | 0.514 at 640, 0.525 at 560, `UC013` at 480 | grid rows are height-derived and member density is gated |
| loop-flywheel | `circle outside canvas` at 480, `primitive text outside canvas` below | radial radius is not height-derived |
| quadrant, venn | `primitive text outside canvas` at 480 | label ring is not height-derived |
| pyramid | works at 480 (0.69), fails at 440 | tier text runs out of room |
| org-chart | works to 440 (0.71), fails at 400 | tier text runs out of room |
| architecture, flowchart, swimlane | accepted but flat or worse (`swimlane` 0.674 -> 0.60) | layout is width-driven |
| layer-stack, state-machine | monotonic gain (`layer-stack` 0.574 -> 0.77) | height-driven layout |

So the knob is a framing control on every data chart and notation diagram, and a utilization
mitigation only on the kinds whose marks do not scale with the canvas. Recorded as a known limit:
radial geometry still rejects a shorter frame on `loop-flywheel`, `quadrant`, and `venn`.

## 4. Remaining limits

Known, bounded, and non-blocking.

- Canvas utilization for `timeline` (0.360) and `tree` (0.375) is the lowest in the catalog, with
  `donut-chart` (0.471) next. The explicit `height` knob mitigates `timeline` and `tree`, measured at
  0.476 and 0.506 on a 400-high canvas. It is a no-op for `donut-chart`, whose radius is
  height-derived, and rejected by `loop-flywheel`, `quadrant`, and `venn`, whose radial geometry is
  not. See section 3.1.
- Sibling connectors in `tree` now merge into one shared horizontal bus per parent, matching
  `org-chart`. The routing moved off the `scene.edges` channel, because `DG112` (connector overlap)
  and `DG115` (shared attach point) iterate `scene.edges` only and reject an edge-channel trunk.
  `structural.py:_tree_bus_scene` rewrites the resolved scene into `ScenePolyline` connectors plus
  manual chevrons and clears `scene.edges`; `compiler.py:_primitive_connectors` restores the edge and
  bend metrics from those primitives so `tree` still reports 9 edges and 17 bends. Nodes stay on the
  `scene.nodes` channel, so focal emphasis, subtitles, reading order, and the DG100-DG111 text gates
  are unchanged.
- `references/fixtures/minimal/*` are contract fixtures, not catalog kinds; several report `VQ101` or
  `VQ102` `TASTE` diagnostics by design.
- `references/fixtures/tabular/*.json` and `uml-class-demo.json` remain in V2 envelope form and
  report `CP002` compatibility diagnostics as expected.
- `dense-architecture-demo.json`, `drawing/data-platform.drawing.json`, and `flowchart/dense.json`
  are deliberate stress fixtures and keep their density warnings.
- `motion` variant cannot be visually verified in a static pipeline; the test asserts CSS presence
  plus byte-identical PNG degradation.
- `motion` is rejected outright for PPTX host slots and for the host integration source builder,
  because a raster export cannot carry a CSS reveal. HTML hosts accept it.

## 5. Reproduction

```bash
python3 scripts/build.py --check
python3 scripts/build.py --sync
python3 scripts/build.py --verify
python3 scripts/folio.py diagram-catalog --baseline references/fixtures/drawing/catalog-baseline-v3.json

python3 scripts/folio.py batch-render-drawings references/fixtures/showcase \
  --output-dir build/showcase/png --format png --profile artifact
python3 scripts/folio.py batch-render-drawings references/fixtures/showcase \
  --output-dir build/showcase/svg --format svg --profile artifact
```

The regression command is `python3 -m unittest discover -s tests`.

## 6. Verdict

The catalog meets every reference editorial principle it set out to adopt and exceeds the reference
project's type breadth, with each principle backed by an executable gate rather than prose. Two
substantive compromises were open at the start of this pass. Shared sibling routing in `tree` is now
closed: connectors moved to the primitive channel and siblings drop from one horizontal bus per parent.
The exact-canvas assertion is also closed: `height` is now a bounded, schema-enforced knob on all
eleven data-chart and notation kinds. One compromise remains, canvas utilization on the single-axis
and shallow-hierarchy kinds (`timeline` 0.360, `tree` 0.375), where the `height` mitigation is a no-op
for `donut-chart` and rejected by `loop-flywheel`, `quadrant`, and `venn`. See section 3.1. No P0 or
P1 finding remains open.
