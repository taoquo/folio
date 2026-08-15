# Drawing DSL V6 Final Audit

Scope: closing audit for the Drawing DSL program. This document records the objective state of the
twenty-two-kind generator catalog against the reference editorial principles, the project's own
quality gates, and a full visual pass over a purpose-built showcase corpus.

Status: complete
Audit date: 2026-08-15
Predecessor: `drawing-dsl-v5-final-audit.md`

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
| Catalog breadth | 22 generator-backed kinds against the reference project's 13 | Exceeded |

Folio additionally enforces properties the reference project leaves to the author: deterministic
layout, fail-closed validation, accessibility reading order (`AX200`-`AX203`), and theme/knob/variant
separation from payload (ADR 0008).

## 2. Showcase visual audit

A dedicated 22-file corpus under `references/fixtures/showcase/` was authored on a single subject
("Orbital Publishing Platform") so that every kind is exercised with realistic content rather than
minimal contract data. All 22 were rendered to PNG and SVG under the `artifact` profile and reviewed
one by one.

| Check | Result |
|---|---|
| Compile diagnostics across 22 showcase fixtures | 0 diagnostics of any level |
| PNG render | 22 rendered, 0 failed |
| SVG render | 22 rendered, 0 failed |
| Manual visual review | 22 / 22 reviewed, 22 / 22 accepted |

### 2.1 Defects found and fixed in this pass

| Defect | Root cause | Fix |
|---|---|---|
| Swimlane edge labels landed on lane borders or outside the canvas | Lane chrome and canvas padding were not label-placement obstacles | Lane borders, lane titles, and stack margins registered as obstacles and passed into `route_graph_edges` |
| Edge labels drifted onto a neighbouring connector | Candidate boxes only moved perpendicular to the segment | Added `ALONG_FRACTIONS` so a label slides along its own segment before changing segment |
| Donut legend read `46% - 46.0%` | Share was appended even when the unit already was a percentage | Share suffix suppressed when `unit` is `%` |
| Sibling connectors crossed in tree and org-chart | Fan-out order was alphabetical by id | Fan-out ordered by the opposite endpoint's coordinate |
| Bar-chart value labels collided with reference lines | Reference line drawn over label text | Knockout rect behind each value label in the canvas fill |

### 2.2 Gate evidence

| Check | Result |
|---|---|
| 26-module regression | `Ran 284 tests` -> `OK (skipped=3)` |
| `build.py --check` | `OK: no violations across 30 templates` |
| `build.py --sync` | `OK: tokens in sync across 30 template(s)` |
| `build.py --verify` | exit 0, zero error lines |
| `diagram-catalog --skip-dsl-build` | `OK: diagram catalog: 22 types, 22 Drawing DSL, 0 HTML baselines` |

## 3. Canvas utilization measurement

Content-bounds utilization was measured for all 22 showcase renders on the default 960 x 540 canvas.
Every kind clears `VQ101` (>= 0.08) and `VQ102` (no dominant margin), but utilization is not uniform.

| Band | Kinds |
|---|---|
| 0.50 - 0.68 | sequence, gantt, org-chart, swimlane, scatter, er-diagram, bar-chart, waterfall, line-chart, flowchart, uml-class, candlestick, layer-stack, quadrant |
| 0.37 - 0.47 | architecture, state-machine, venn, tree |
| 0.20 - 0.33 | timeline, loop-flywheel, donut-chart, pyramid |

The low band is intrinsic to the geometry: a radial or single-axis composition cannot fill a 16:9
rectangle without inflating marks past the type scale. Authors who want a tighter frame set
`height` explicitly; on `timeline`, `height: 400` raises utilization from 0.32 to 0.43 with zero new
diagnostics. Changing the shipped default would move every committed geometry baseline, so the
default stays 960 x 540 and the knob is documented instead.

## 4. Remaining limits

Known, bounded, and non-blocking.

- Canvas utilization for `timeline`, `loop-flywheel`, `donut-chart`, and `pyramid` is 0.20 - 0.33 on
  the default canvas. Mitigation is the explicit `height` knob, per section 3.
- Sibling connectors in `tree` and `org-chart` fan out as staggered orthogonal runs rather than
  merging into one shared trunk. A shared trunk necessarily violates `DG112` (connector overlap) and
  `DG115` (shared attach point), so the staggered form is the only gate-legal solution.
- `references/fixtures/minimal/*` are contract fixtures, not catalog kinds; several report `VQ101` or
  `VQ102` `TASTE` diagnostics by design.
- `references/fixtures/tabular/*.json` and `uml-class-demo.json` remain in V2 envelope form and
  report `CP002` compatibility diagnostics as expected.
- `dense-architecture-demo.json`, `drawing/data-platform.drawing.json`, and `flowchart/dense.json`
  are deliberate stress fixtures and keep their density warnings.
- `motion` variant cannot be visually verified in a static pipeline; the test asserts CSS presence
  plus byte-identical PNG degradation.
- `review.py:write_review_bundle`, `hosting.py`, and `drawing_host_integration.py` still embed with
  the default `folio` theme and `plain` variant.

## 5. Reproduction

```bash
python3 scripts/build.py --check
python3 scripts/build.py --sync
python3 scripts/build.py --verify
python3 scripts/folio.py diagram-catalog --skip-dsl-build

python3 scripts/folio.py batch-render-drawings references/fixtures/showcase \
  --output-dir build/showcase/png --format png --profile artifact
python3 scripts/folio.py batch-render-drawings references/fixtures/showcase \
  --output-dir build/showcase/svg --format svg --profile artifact
```

The 26-module regression command is listed in `drawing-dsl-v5-final-audit.md` and is unchanged.

## 6. Verdict

The catalog meets every reference editorial principle it set out to adopt and exceeds the reference
project's type breadth, with each principle backed by an executable gate rather than prose. The two
substantive compromises are canvas utilization on four radial or single-axis kinds and staggered
sibling routing in hierarchy kinds; both are documented above with the reason they are not defects to
be fixed. No P0 or P1 finding remains open.

