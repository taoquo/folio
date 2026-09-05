# Folio Drawing DSL

Folio's Drawing DSL is an executable visual-intent layer for generator-backed diagrams. It is not an SVG authoring language.

## Current scope

The Drawing DSL covers twenty-three registered types. Architecture, Flowchart, State Machine, Swimlane, Tree, Layer Stack, Timeline, Quadrant, Venn, Pyramid, Org Chart, Loop Flywheel, Bar, Line, Donut, Candlestick, Waterfall, Scatter, Gantt, Heatmap, Sequence, UML Class, and ER Diagram all compile through the shared registry. The hand-authored HTML/SVG files and legacy UML loader remain compatibility references and manual escape hatches.

The compiler stages are:

```text
normalized input -> compiler registry -> type semantic IR -> type plan
                 -> deterministic layout -> ResolvedScene
                 -> canvas + primitive + accessibility validation
                 -> SVG / PNG / PDF output profile
```

Every registered compiler returns a `CompilationResult` containing normalized input, semantic IR, plan, layout, scene, diagnostics, metrics, output profile, and stable compilation metadata. Any `ERROR` stops artifact creation.

## Boundaries

`SemanticDiagram` answers what exists and what matters: entities, relationships, roles, ownership, lifecycle, groups, narrative focus, and evidence-backed labels. It contains no coordinates, dimensions, colors, font sizes, radii, or paths.

`DrawingPlan` answers how meaning should be encoded. Its intentionally small vocabulary is:

- composition: `layered`, `pipeline`, `hub`
- axis: `top-down`, `left-right`
- node archetype: `component`, `datastore`, `external`, `cloud`
- edge channel: `primary-flow`, `secondary-flow`, `async-flow`
- emphasis: `focal`, `normal`, `background`
- region treatment: `layer-band`, `soft-boundary`, `none`
- information reduction: `merge`, `drop`, `background`, `split`

Reduction decisions are serialized with their targets, reason, and whether they were applied or emitted as a recommendation. This keeps deletion-first planning reviewable without silently collapsing semantic entities.

`ResolvedScene` contains final geometry, resolved styles, text runs, arrows, z-order, and type-neutral rect, line, polyline, path, circle, text, group, and clip primitives. It is the only input accepted by the shared SVG renderer.

## Responsibility split

- Semantic planner: selects information, relationships, focus, spine, and groups.
- Drawing planner and grammar: select composition, archetypes, hierarchy, spacing, ports, text roles, and theme roles.
- ELK backend: solves constrained geometry.
- Scene resolver: resolves exact geometry, typography, connectors, and theme values.
- Renderer: serializes the resolved scene. It does not branch on focus, importance, node kind, or asynchronous semantics.

## V2 additions

- Architecture plans use the versioned `2.0` authoring contract in `references/schemas/drawing-plan-v2.schema.json`; missing versions migrate deterministically from V1.
- Flowchart input uses `references/schemas/types/flowchart.schema.json` and a type-specific semantic, plan, layout, and validation grammar.
- Architecture nodes choose exactly one content-driven tier: `compact` 144 x 64, `regular` 176 x 72, or `wide` 224 x 80.
- Typed annotations, first-class legends, trust boundaries, phase bands, and twelve built-in semantic pictograms resolve into shared scene primitives.
- Architecture layout evaluates at most eight grammar-approved candidates and selects lexicographically by errors, connector violations, crossings, spine bends, total bends, spacing variance, and stable candidate name.
- Dense Architecture plans can be explicitly transformed into a `DrawingBundle` containing an overview, bounded detail plans, and complete node navigation.
- SVG output includes a title, description, language, stable node ids, and deterministic reading-order metadata.
- Review bundles contain semantic, plan, layout, scene, SVG, PNG, PDF, manifest, and optional perceptual diff artifacts.

## V3 platform

- `DiagramCompilerRegistry` dispatches all registered types through one fail-closed boundary.
- `CompilationResult` records normalized input, output profile, diagnostics, metrics, schema version, registry key, and input digest.
- Canvas, primitive, accessibility, type, geometry, and taste checks have explicit stage ownership.
- Output profiles are `artifact`, `embed`, and `page-preview`; the latter removes static minimum widths and validates fitted review bounds.
- SVG, PNG, and PDF are exercised for every type across all three profiles; the V5 matrix contains 198 artifacts.
- Catalog manifest 3.0 records profile, source/output dimensions, content bounds, diagnostics, metrics, registry keys, versions, and SHA-256 digests for twenty-three generator-backed entries.
- Review manifests preserve dimension mismatches instead of resizing them away and record an explicit approval state.
- Host manifest 1.1 and review manifests both record the resolved `theme` and the render `variant`, and `verify-drawing-host` rejects variant metadata drift.
- Structural grammars own reachability, ownership, hierarchy, transition, lane, and layer invariants.
- Positional grammars own temporal order, axis domains, label candidates, and bounded set topology.
- Data Viz Core owns finite-number checks, missing-value policy, locale/unit formatting, deterministic scales and ticks, stable mark ids, temporal spacing, OHLC validation, and cumulative arithmetic.

## V4 developer surface

- Every registered kind has one authoritative schema under `references/schemas/types/`, plus one minimal and one canonical compiling fixture.
- The schema registry is exactly aligned with the production compiler registry and supplies schema versions, portable paths, profiles, and formats to the public CLI.
- Architecture semantic input is normalized to schema version `3.0`; compatible unversioned input migrates idempotently, while expert Architecture DrawingPlan input remains on `2.0`.
- `list-diagram-types`, `init-drawing`, `validate-drawing`, `render-drawing`, and `batch-render-drawings` form the small public workflow. V3 commands remain compatible aliases and inspection tools.
- Batch output order and names are deterministic, same-named source files cannot collide, and invalid inputs never leave partial artifacts.
- Sequence, UML Class, and ER Diagram use coordinate-free `3.0` notation contracts, stable object and relationship ids, shared scene validation, output profiles, accessibility metadata, and host integration.

## V5 semantic routing

V5 adds an explicit routing layer in front of the compiler registry. It answers one question before any geometry exists: given a communication intent, which diagram kind should carry it?

The eight semantic patterns are `architecture`, `comparison`, `data`, `flow`, `hierarchy`, `relationship`, `state`, and `time`. Every pattern owns an ordered list of candidate kinds, so a tie always resolves the same way.

A routing request carries semantics only, never pixels:

- `content`: the author brief, scored against a shared English and Chinese cue table.
- `audience`: `executive`, `general`, or `practitioner`.
- `goal`: `compare`, `convince`, `explain`, or `track`.
- `pattern_hint` / `kind_hint`: explicit author overrides.
- `shape`: coarse counts and flags such as `node_count`, `series_count`, `depth`, `has_time_axis`, `has_cycle`, `has_actors`, and `numeric`.

Scoring is deterministic: each keyword hit adds 3, each shape signal adds 2, and an author hint adds 12. When the top two patterns land within a margin of 2, the router still decides but reports the ambiguity and lowers confidence to `low`. The contract lives in `references/schemas/route-request.schema.json`.

Every decision returns the winning pattern and kind, a confidence band, the full per-pattern score table, in-pattern alternatives, and a step-by-step trace, so a routing choice can always be explained and reviewed.

Routing diagnostics are:

- `RT001` ERROR: nothing matched; the brief may not be drawable at all.
- `RT002` WARNING: two patterns scored within the ambiguity margin.
- `RT003` ERROR: unknown pattern hint.
- `RT004` ERROR: kind hint belongs to no registered pattern.
- `RT010` WARNING: unknown audience, falling back to `general`.
- `RT011` WARNING: unknown goal, falling back to `explain`.

```bash
python3 scripts/folio.py route-diagram --content "the approval process flow"
python3 scripts/folio.py route-diagram /tmp/route-request.json --format json --output /tmp/route.json
```

Routing never writes artifacts. It recommends a kind; authoring, compiling, and validating stay unchanged.

## V5 output layer

Size, detail, audience, and variant are render-layer knobs. They live in `scripts/drawing/output/` and are applied after layout, never inside a payload. Adding any of them to a diagram payload fails validation with `ERROR BC000: unknown field`.

| Knob | Values | Effect |
|---|---|---|
| `--size` | `compact` 1280 / `standard` 1920 / `wide` 2560 | Raster export width only. Scene geometry is unchanged. |
| `--detail` | `essential` / `standard` / `full` | `full` keeps every gridline; `standard` keeps every other gridline; `essential` drops all gridlines and annotations. |
| `--audience` | `executive` / `general` / `practitioner` | Only `executive` acts: text below 10pt is bumped by 1pt for projector legibility. |
| `--variant` | `plain` / `sketchy` / `motion` | `sketchy` adds a turbulence displacement filter to shape strokes; `motion` adds a reduced-motion-aware staggered reveal keyed to `data-reading-order`. |

Detail filtering removes scene elements and rewrites `reading_order` in the same pass, so `AX200`-`AX203` stay satisfied. No knob may introduce an accent-bearing element, which keeps ADR 0006 intact.

Two documented degradations:

- `page-preview` renders a fixed A4 raster, so `--size` is ignored and the CLI prints a warning.
- `motion` is CSS-driven, so PNG and PDF exports render byte-identically to `plain` and the CLI prints a warning.

```bash
python3 scripts/folio.py render-drawing references/fixtures/v3/bar-chart.json \
  --profile artifact --format png --size compact --detail essential \
  --audience executive --variant sketchy --output /tmp/bar.png

python3 scripts/folio.py batch-render-drawings references/fixtures/v5 \
  --output-dir /tmp/folio-wide --format svg --size wide --variant motion
```

## Invariants

- Agent-produced intent cannot set `x`, `y`, width, height, hex colors, font sizes, stroke widths, radii, or exact paths.
- Architecture generator geometry comes from `scripts/drawing/grammar/architecture.py`; later structural, positional, and data grammars live in their matching type modules.
- Folio palette and font families come from `scripts/drawing/theme/folio.py`.
- Geometry is compiler-owned and snapped to the type's deterministic layout grid.
- Information budgets and focal limits are type-specific and fail closed when exceeded. What the budget is measured against depends on the canvas mode -- see [Canvas modes](#canvas-modes).
- Connectors use orthogonal segments, 8-unit rounded elbows, distinct attach points, opaque label masks, and bridge hops at unavoidable crossings.
- Folio keeps one accent color.
- Architecture SVG, PNG, and PDF artifact entrypoints remain compatible.
- The coordinate-bearing UML loader in `scripts/diagram_models.py` plus `scripts/diagram_layout.py:layout_uml_class` remain available only as a compatibility facade; production UML artifacts use the coordinate-free registry contract.
- `scripts/diagram_models.py` is the Architecture spec contract shared by the registry compiler and `scripts/diagram_semantic_planning.py`; the latter is the supported text-to-Architecture planner, not a legacy path.

## Canvas modes

Run `python3 scripts/build_canvas_review.py` to regenerate the offline comparison at
`build/canvas/index.html`. It includes host placement illustrations, compiler-generated
artifacts, full-size viewing, and executable rejection cases.

Every payload declares a 960-unit-wide stage. Architecture keeps that width; existing
adaptive families such as Flowchart can resize the resolved scene. Height is a declared
knob, and `canvas` says which rules govern it.

| | `"canvas": "figure"` (default) | `"canvas": "poster"` |
|---|---|---|
| Width | 960 | 960 |
| Height, graph families | 500-800 | 500-4000 |
| Height, notation families | 480-800 | 480-4000 |
| Height, chart families | 400-720 | 400-2400 |
| Height when omitted | existing family default/layout behavior | derived for Architecture, Gantt, Heatmap; existing behavior for others |
| Architecture node budget | editorial, 9 | canvas capacity, at most 265 |
| Gantt/Heatmap row budget | editorial, 10 | proportional to height, at most 44 |
| Intended use | a figure inside a document | the diagram is the artifact |

A figure is an illustration sitting in a column of text, so it keeps the deletion-first
budget: nine architecture nodes, ten gantt tasks. That budget is a position about what
belongs in a figure, and extra height does not change the answer.

A poster is the artifact itself. It may grow downward until its content is placed, and its
budget follows the canvas:

```json
{
  "kind": "architecture",
  "canvas": "poster",
  "layers": [ /* twelve tiers */ ],
  "nodes": [ /* sixty nodes, five to a tier */ ]
}
```

Omitting `height` is the normal case: asking an author to both add nodes and compute the
canvas that holds them is asking them to do the layout's job. The example above resolves to
1020 units.

### Two kinds of capacity

The rule differs by whether content is placed at a fixed size or compressed to fit.

**Fixed-size content** -- regular architecture node boxes stay 144x64 and their type stays 7/11/12 SVG user units
at every count, so what bounds them is the pitch below which the layout reports an overlap.
Measured at 72 units, giving `(height - 228) // 72 + 1` rows of five. Sixty nodes need 1020
units; two hundred need 3036.
This is an estimate for layered regular nodes, not an automatic wrapping algorithm or a
guarantee for wide nodes, sidecars, hub layouts, labels, or densely crossed connectors.
All geometry and routing checks still run. SVG user units become physical points only
after placement scaling; they are not a promise of final print type size.

**Elastic content** -- chart rows compress, so forty gantt tasks fit inside 668 units and are
unreadable there. Their ceiling protects density instead: a poster carries proportionally
more rows because it has proportionally more room, and each row keeps the height it had in a
figure. Ten rows at 540 and forty rows at 2160 both sit at roughly 54 units per row.
This is a conservative full-canvas ratio; fixed chart chrome means the plot-row pitch is
not exactly constant. Gantt and Heatmap derive this height before validating the 2400 ceiling.

### Failing closed is preserved

A poster is still a bounded canvas. `DG002` fires when a payload exceeds what its canvas
places; only the number it compares against becomes honest. Both modes name the remedy:

```
ERROR DG002: 10 nodes exceed budget 9
  hint: set "canvas": "poster" to grow the canvas, or split the diagram

ERROR DG002: 40 nodes exceed budget 25
  hint: raise height to 732 or split the diagram
```

### Posters and embedding

`embed-drawing` rejects posters for every current host: A4, Letter, 16:9 slides, and ordinary
responsive HTML slots. The check runs before writing an artifact. Verification also reads
the fixture's mode, so an older manifest cannot bypass the restriction. Use standalone
`artifact` SVG/PNG/PDF, or an explicitly scrollable web viewer with full-size access. There
is no implicit splitting, content deletion, or override that silently shrinks a poster.

Figures contain-fit the host slot. A height-driven fit must retain at least 75% of its
width-fit scale; otherwise embedding fails and asks for a shorter figure, a larger slot, or
linked details. This is a geometric safeguard, not a legibility certificate. The manifest
records the predicted physical minimum font size and emits warnings below 6pt in print,
12pt in slides, or 12px in the nominal responsive slot. Existing small labels may trigger
these warnings. CLI output surfaces them; HTML verification checks the emitted fit styles
and SVG type sizes, and PPTX verification checks actual image placement. Browser zoom,
overriding host CSS, page pagination, and a responsive viewport narrower than the declared
slot still require final visual review.

### Independent complexity limits

Architecture posters have absolute safety ceilings of 265 nodes and 530 edges; their
4000 height ceiling also applies to automatically derived heights and direct plan inputs.
These are operational limits, not recommended diagram sizes. `DG203` requests an overview
and linked details at 30 nodes, and `DG205` warns above 45 edges, independently of canvas
height. Figures keep their existing complexity thresholds. Focus, crossing, and label
checks remain active in both modes.

### What poster mode does not change

- **Five nodes to a row.** That is the width constraint, and width is fixed in both modes.
- **Height floors.** Below 500 a graph's radial and quadrant label rings collide, in any mode.
- **Semantic caps.** `donut requires 2-6 segments` and `venn supports exactly two or three
  sets` are claims about the chart, not about the room. A nine-slice donut is a worse chart,
  not a bigger one, so those ceilings do not move.
- **Crossing connectors.** Fully crossed layers report `LY001` at ten nodes just as at forty;
  that is a routing limit, independent of canvas size.

## Diagnostics

Diagnostics are explicit and actionable:

- `ERROR`: deterministic invalid output, such as overlap, detached endpoints, invalid vocabulary, or budget violations.
- `WARNING`: valid but pressured output, such as excessive labels or degraded text fit.
- `TASTE`: explainable editorial concerns, such as excessive spine bends or high density.

There is no aggregate aesthetic score.

The V4 JSON envelope contains `code`, `severity`, `stage`, `kind`, `path`, `message`, `hint`, and `related_ids`, sorted by stage, code, path, and related id. CLI exit codes are 0 for success, 1 for invalid input, 2 for dependency or file/export failure, and 3 for an internal command failure.

## Development commands

```bash
python3 scripts/folio.py list-diagram-types --format json
python3 scripts/folio.py route-diagram --content "quarterly revenue by region" --goal compare
python3 scripts/folio.py init-drawing timeline --output /tmp/timeline.json
python3 scripts/folio.py validate-drawing /tmp/timeline.json --format json
python3 scripts/folio.py batch-render-drawings references/fixtures/minimal --output-dir /tmp/drawing-batch --report-format json
python3 scripts/folio.py draw-semantic references/fixtures/architecture-demo.json
python3 scripts/folio.py draw-plan references/fixtures/architecture-demo.json --explain-drawing
python3 scripts/folio.py draw-scene references/fixtures/architecture-demo.json
python3 scripts/folio.py draw-layout references/fixtures/architecture-demo.json
python3 scripts/folio.py draw-metrics references/fixtures/architecture-demo.json
python3 scripts/folio.py check-drawing references/fixtures/architecture-demo.json --explain-drawing
python3 scripts/folio.py validate-drawing-schema references/fixtures/v5/heatmap.json
python3 scripts/folio.py validate-drawing-schema references/fixtures/drawing/agent-runtime.drawing.json
python3 scripts/folio.py render-drawing references/fixtures/v3/waterfall.json --profile embed --format svg --output /tmp/waterfall.svg
python3 scripts/folio.py review-drawing references/fixtures/v3/state-machine.json --profile page-preview --output-dir /tmp/state-review
python3 scripts/folio.py diagram-catalog --skip-dsl-build
python3 scripts/folio.py diagram-catalog --baseline references/fixtures/drawing/catalog-baseline-v3.json --baseline-report /tmp/catalog-baseline-report.json
python3 scripts/folio.py migrate-drawing references/fixtures/drawing/agent-runtime.drawing.json --output /tmp/agent-runtime-v2.json
python3 scripts/folio.py bundle-drawing references/fixtures/drawing/agent-runtime.drawing.json --output /tmp/agent-runtime-bundle.json
```

Each command also accepts a raw-text fixture. Use `--title` to set its title and `--output` on the JSON-producing commands to write a snapshot.

`draw-plan`, `draw-scene`, and `check-drawing` also accept a handwritten DrawingPlan JSON file containing a top-level `composition` object. This is the expert authoring path. It still permits only semantic and layout intent; pixel overrides remain unavailable.

`draw-metrics` emits semantic and visual node counts, edges, visible labels, focal count, crossings, bends, spine bends, text overflow, layout warnings, and taste warnings for deterministic regression review.

The approved page-preview baseline lives at `references/fixtures/drawing/catalog-baseline-v3.json`. It locks registry keys, semantic reading-order ids, dimensions, content bounds, input and SVG digests, and approved PNG evidence. Catalog comparison rejects missing artifacts, semantic-id changes, dimension changes, bounds movement beyond tolerance, source changes, and unapproved large pixel differences. Creating or replacing a baseline requires `--write-baseline` together with a non-empty `--approval-reason`.

The intent-first workflow, per-type example policy, stable diagnostics, and batch behavior are documented in `drawing-dsl-authoring.md`.

## Design reference

The constrained vocabulary, single focal accent, 4-unit grid, and deletion-first information budget are informed by the editorial principles in [diagram-design](https://github.com/cathrynlavery/diagram-design). Folio implements those principles through its own compiler, theme, and artifact pipeline rather than importing the reference project's HTML templates.

The closing program audit, including reference-principle conformance, the 23-kind showcase visual pass, and remaining limits, is `drawing-dsl-v6-final-audit.md`. Superseded release plans and per-version acceptance records for V2 through V5 are kept for history in `references/archive/`.
