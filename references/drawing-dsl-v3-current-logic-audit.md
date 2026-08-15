# Folio Drawing DSL Current Logic Audit

Status: closed — all findings remediated and verified  
Audit date: 2026-08-12  
Scope: current Drawing DSL Core, Architecture, Flowchart, layout, scene, validation, renderer, CLI, export, catalog, review, and tests  
Execution response: `drawing-dsl-v3-completion-goal.md`

## 0. Closure record

Closure date: 2026-08-13

| Finding | State | Closure evidence |
|---|---|---|
| AUD-001 | closed | Shared registry and `CompilationResult`; every public compile, render, review, layout, scene, and metric path fails closed. |
| AUD-002 | closed | Flowchart expands bounded breadth and rejects any remaining invalid scene before export. |
| AUD-003 | closed | Layout edges preserve stable ids; parallel routes and labels have a regression fixture. |
| AUD-004 | closed | Explicit output profiles remove minimum-width clipping; all fourteen page previews have raster bounds evidence. |
| AUD-005 | closed | Flowchart validates starts, terminals, decisions, branch labels, convergence, focus, reachability, duplicates, and loop complexity. |
| AUD-006 | closed | Runtime normalization is mandatory, published schemas are structural, and contract parity has regression coverage. |
| AUD-007 | closed | Architecture candidates use deterministic lexicographic geometry, violations, crossings, spine bends, bends, spacing, and key criteria. |
| AUD-008 | closed | Semantic spine reversal was removed from candidate generation and snapshots were regenerated from declared order. |
| AUD-009 | closed | Layout warnings are compiler errors; an overflowing Architecture layout cannot reach scene export. |
| AUD-010 | closed | Pictograms and other vocabularies reject at schema or grammar stages instead of leaking lookup errors. |
| AUD-011 | closed | Missing routes, unplaceable annotations, and oversized legends produce explicit compiler errors. |
| AUD-012 | closed | Flowchart reading order contains every node exactly once; SVG fallback indexes are unique. |
| AUD-013 | closed | Visual comparison records both dimensions and pads without resizing either input. |
| AUD-014 | closed | PDF metadata is escaped, scene language is propagated, and profile-specific page sizing is explicit. |
| AUD-015 | closed | Layout endpoints must touch node boundaries. |
| AUD-016 | closed | Canvas, primitive, accessibility, and graph geometry validators are separate and shared validators import no type grammar. |
| AUD-017 | closed | Focus paths, background nodes, direction, and route policy are validated and restricted to implemented behavior. |
| AUD-018 | closed | Malformed SVG produces an explicit source-validation issue. |
| AUD-019 | closed | Catalog paths, custom fixtures, contact sheets, and temporary HTML work inside or outside the repository. |
| AUD-020 | closed | Review manifests record versions, profile, dimensions, bounds, diagnostics, metrics, digests, diff method, and approval state; catalog manifests record the applicable release evidence. |
| AUD-021 | closed | Gate S adds invalid-stage, dense, parallel, accessibility, profile, malformed-source, catalog portability, and dimension regressions. |

The findings below remain as the historical problem statement. The closure table is authoritative for current status.

## 1. Executive verdict

The current V2 implementation is a useful prototype baseline, but it is not safe to use as the foundation for twelve additional compilers without a stabilization phase.

The primary problem is not a single renderer bug. Compilation, checking, and exporting are separate paths. Some invalid inputs are rejected by explicit check commands, some crash later with implementation exceptions, and some compile and export while already containing known semantic or geometry errors. This makes the public behavior inconsistent and allows successful commands to overstate artifact validity.

The audit confirmed:

- 4 P0 release blockers;
- 10 P1 high-severity correctness or contract defects;
- 7 P2 medium-severity reliability, portability, or observability defects;
- no confirmed shell-command injection in the reviewed subprocess calls;
- correct XML escaping for authored node and text content in the shared SVG renderer.

V3 implementation must begin with Gate S in the completion goal. New diagram grammars should not be added first.

## 2. Method

The audit used four evidence sources:

1. Contract review against `drawing-dsl.md`, `drawing-dsl-v2-plan.md`, `drawing-architecture.md`, `drawing-dsl-v3-plan.md`, `diagrams.md`, and `production.md`.
2. Static inspection of schema, models, planners, layouts, resolvers, validators, renderer, export, CLI, catalog, and test code.
3. Runtime probes using minimal in-memory payloads without changing production code.
4. Existing catalog images and build verification results.

Severity means:

- P0: blocks the V3 platform or can produce a materially invalid artifact while reporting success.
- P1: breaks a documented contract, loses semantics, causes inconsistent failure, or weakens a release gate.
- P2: reliability, portability, diagnostics, or hardening issue that should be fixed during V3.0.

## 3. Confirmed P0 findings

### AUD-001 — Compilation and export are fail-open

Affected code:

- `scripts/folio.py::_compile_drawing_input`
- `scripts/drawing/pipeline.py::compile_architecture`
- `scripts/drawing/pipeline.py::compile_drawing_plan`
- `scripts/drawing/flowchart.py::compile_flowchart_payload`

Evidence:

- A Flowchart payload with no `schema_version` and an unknown top-level field compiled successfully.
- An Architecture plan whose spine referenced `missing-node` produced `DG007` and `DG010` when checked directly, but `compile_drawing_plan` still returned a scene with no warnings.
- `render-drawing`, `draw-scene`, `draw-layout`, and `review-drawing` call compilation and export without enforcing the diagnostics used by `check-drawing`.

Impact:

- A successful render does not mean the plan or scene is valid.
- Each new type could accidentally implement a different validation order.
- Invalid inputs have three inconsistent outcomes: accepted, silently degraded, or late implementation exception.

Required fix:

- One shared compilation orchestrator must normalize, validate, lay out, resolve, validate the scene, and only then permit export.
- All CLI and build consumers must use the same `CompilationResult`.

Acceptance:

- Any `ERROR` prevents artifact creation and produces a stable diagnostic with a non-zero exit code.

### AUD-002 — A valid-budget dense Flowchart compiles into invalid geometry

Affected code:

- `scripts/drawing/flowchart.py::layout_flowchart`
- `scripts/drawing/flowchart.py::compile_flowchart_payload`

Reproduction:

- 11 nodes, one decision, and eight branch nodes fit the documented 12-node and 4-decision budgets.
- Compilation succeeded.
- Layout bounds were `x=-328, y=88, w=1616, h=440` for a `960 x 540` scene.
- Post-hoc geometry validation produced `DG100`, `DG109`, `DG110`, and `DG112` errors.

Root cause:

- Nodes at one depth use fixed widths and a fixed 48-unit gap without a fit, split, or rejection policy.
- The compiler does not run scene geometry validation.

Impact:

- Legal semantic input can produce clipped nodes, arrows outside the canvas, edge-through-node violations, and connector overlap.

Required fix:

- Add bounded breadth handling, a deterministic split/compact policy, and mandatory post-layout validation.

### AUD-003 — Parallel Flowchart edges collapse and copy the last label

Affected code:

- `scripts/drawing/flowchart.py::resolve_flowchart_scene`

Evidence:

- Layout created two distinct routes for edges `a` and `b` between the same nodes.
- Scene resolution indexed routes as `{(source, target): edge}`.
- The two scene edges became one identical route and both labels became `B`.

Impact:

- Relation identity, route geometry, and labels are lost.
- State Machine and data-flow extensions would inherit the same failure if they copied this resolver pattern.

Required fix:

- Match by stable edge id, or use a deterministic per-pair queue as Architecture does.

### AUD-004 — Build verification accepts horizontally clipped diagram exports

Affected code:

- `scripts/build.py::verify_target`
- `scripts/diagram_geometry.py::validate_diagram_html`
- static diagram CSS with `svg { min-width: 780px–860px; }`

Evidence:

- State Machine, Timeline, Swimlane, Tree, Layer Stack, and Venn visibly clip in the A4 catalog preview.
- Existing verification passes because it checks render success, page count, fonts, and limited source-SVG rect/text bounds.
- It does not validate fitted page bounds or raster/PDF content clipping.

Impact:

- A one-page PDF can be structurally successful and visually incomplete.
- V3 release evidence would be unreliable without profile-aware post-export checks.

Required fix:

- Add explicit output profiles and validate content bounds after profile fitting in all formats.

## 4. Confirmed P1 findings

### AUD-005 — Flowchart type validation implements only part of the published grammar

Affected code:

- `scripts/drawing/flowchart.py::validate_flowchart`
- `scripts/drawing/schema.py::_validate_flowchart_payload`

Confirmed accepted invalid cases:

- empty Flowchart;
- a `terminal` node with outgoing flow;
- a decision whose conditional exits have no readable labels;
- unknown or missing focus silently producing no focal node;
- duplicate node and edge ids;
- branches without convergence or explicit termination;
- nested loops deeper than the documented maximum of two.

The V2 plan explicitly requires short conditional labels, valid exits, convergence or termination, legal loop structure, reachability, and readable branch labels.

Impact:

- Type notation is not executable source of truth.
- Invalid semantics can pass before layout and accessibility checks.

### AUD-006 — Schema contracts are shallow, duplicated, and bypassed

Affected code:

- `references/schemas/drawing-plan-v2.schema.json`
- `references/schemas/flowchart-v2.schema.json`
- `scripts/drawing/schema.py`

Evidence:

- The JSON Schema files are not loaded by runtime or tests.
- Architecture `composition`, `hierarchy`, `content`, and `edges` are largely untyped in the published JSON Schema.
- The Python validator checks a different subset and does not validate duplicate ids, references, focus paths, background nodes, legend items, dimensions, directions, or route policies.
- Flowchart compilation bypasses `normalize_plan_payload` entirely.

Impact:

- There is no single authoritative authoring contract.
- A payload may conform to one validator and fail or change meaning later.

### AUD-007 — Architecture candidate selection violates its documented criteria

Affected code:

- `scripts/drawing/layout/candidates.py`

Published criteria:

1. zero geometry errors;
2. zero connector overlap and edge-through-node errors;
3. crossing count;
4. spine bends;
5. total bends;
6. spacing variance;
7. stable key.

Actual score:

```text
(number of layout warning strings, total bends, route length, name)
```

Impact:

- Different error severities receive equal weight.
- Crossings, primary-spine bends, and spacing variance are absent.
- A candidate with one severe canvas error can beat a candidate with two mild warnings.

### AUD-008 — Candidate generation mutates the semantic reading path

Affected code:

- `scripts/drawing/layout/candidates.py::rank_layout_candidates`

Evidence:

- `spine-reversed` reverses the declared primary reading path instead of varying a geometric choice.
- It is currently selected for Agent Runtime, Chinese Architecture, and Workflow Engine fixtures because it lowers the incomplete score.
- The selected geometry is based on the reversed spine, while scene resolution and reading-order metadata still use the original plan.

Impact:

- Layout constraints and resolved semantics disagree.
- Primary path straightness can be improved by discarding the intended direction rather than honoring it.

Required fix:

- Never mutate semantic order during candidate generation. Vary only side, lane, ordering strategy, or other grammar-approved geometry.

### AUD-009 — Architecture layouts can overflow and remain selectable

Affected code:

- `scripts/drawing/layout/elk.py::_layered_boxes`
- `scripts/drawing/layout/elk.py::_pipeline_boxes`
- `scripts/drawing/layout/elk.py::_hub_boxes`
- `scripts/drawing/layout/elk.py::layout_drawing`

Evidence:

- When node widths exceed the available row width, layered and pipeline layouts clamp gaps to a positive minimum but do not fit, split, or reject the row.
- Hub radius does not account for satellite width or high satellite counts.
- `validate_layout` findings are stored as warnings; compilation continues.

Impact:

- A selected layout may contain hard geometry errors and still export.

### AUD-010 — Invalid vocabulary can pass schema validation and crash during resolution

Affected code:

- `scripts/drawing/schema.py::validate_plan_payload`
- `scripts/drawing/validation/grammar.py`
- `scripts/drawing/resolve.py::_pictogram`

Evidence:

- `pictogram: not-a-real-pictogram` produced no schema issue.
- Compilation later raised `KeyError` in the pictogram lookup.

Impact:

- A user-facing contract error becomes an internal exception.
- Other vocabulary fields have the same risk because grammar validation is not mandatory.

### AUD-011 — Scene resolution can silently lose or misplace content

Affected code:

- `scripts/drawing/resolve.py::resolve_scene`
- `scripts/drawing/resolve.py::_annotation_scenes`
- `scripts/drawing/resolve.py::_legend_scene`

Evidence:

- An Architecture edge with no matching layout route is silently skipped.
- Annotation placement uses the last candidate even when none is free, then may stop while the annotation remains invalid.
- Legend width has no fit or wrap policy. Six long legend items produced `x=-676, width=2312` on a 960-unit scene.

Additional validator gap:

- `validate_scene_geometry` did not report the out-of-bounds legend because it validates legend grid alignment but not legend bounds or item text containment.

Impact:

- Semantics can disappear or leave the canvas without stopping export.

### AUD-012 — SVG reading-order metadata is incomplete and non-unique

Affected code:

- `scripts/drawing/flowchart.py::resolve_flowchart_scene`
- `scripts/renderers/svg.py::render_svg`

Evidence:

- Flowchart scene reading order contains only the longest spine.
- Any non-spine node receives `data-reading-order="0"`.
- Four of the five current Flowchart fixtures contain duplicate order zero values.

Impact:

- Branch-only nodes do not have a complete logical order.
- The output contradicts the documented deterministic reading-order contract.

### AUD-013 — Perceptual diff hides dimension regressions

Affected code:

- `scripts/drawing/review.py::_visual_diff`

Evidence:

- A 10 x 10 solid image and a 20 x 20 image of the same color returned `changed_channel_ratio: 0.0`.
- The baseline is silently resized to the current dimensions before comparison.

Impact:

- Canvas size, aspect-ratio, and output-profile regressions can be approved as no visual change.

Required fix:

- Dimensions are a separate hard comparison. Any normalization must be explicit, classified, and recorded.

### AUD-014 — PDF export interpolates unescaped HTML and hard-codes language

Affected code:

- `scripts/diagram_export.py::export_pdf`

Evidence:

- Title is interpolated directly inside `<title>`.
- A title containing `</title><script>...</script><title>` appears as markup in the generated HTML.
- The HTML document always uses `lang="en"`, including Chinese scenes.

Impact:

- Authored metadata can break the export wrapper or add unintended resources or elements.
- This is HTML injection, not a confirmed code-execution vulnerability; WeasyPrint does not execute browser JavaScript.
- PDF language metadata is incorrect for non-English artifacts.

Required fix:

- HTML-escape title and metadata, pass scene language, and define a local/remote resource policy.

## 5. Confirmed P2 findings

### AUD-015 — Layout endpoint validation accepts points anywhere inside a node

Affected code:

- `scripts/drawing/validation/layout.py::_point_touches_box`

The function checks whether the endpoint is inside an expanded box, not whether it touches a boundary. Candidate scoring can therefore treat an endpoint buried inside a node as valid. The later scene validator is stricter, but it is not mandatory during compilation.

### AUD-016 — Shared geometry validation is Architecture-specific and incomplete

Affected code:

- `scripts/drawing/validation/geometry.py::validate_scene_geometry`

The validator defaults to `ArchitectureGrammar`, assumes graph nodes and edges, directly indexes arrow point 1, and does not provide type-neutral primitive, canvas, clip, path, or numerical validation. It also omits legend bounds and legend-item text checks.

This is both a current gap and a known V3 design debt.

### AUD-017 — Several authored intent fields are stored but not enforced

Affected fields:

- `HierarchyPlan.focus_path`
- `HierarchyPlan.background_nodes`
- `VisualEdgePlan.direction`
- `VisualEdgePlan.route_policy`

These fields serialize and round-trip, but current layout and resolution either do not validate them or do not use them. This creates silent intent drift and makes the expert authoring contract misleading.

### AUD-018 — Diagram source validation swallows malformed SVG

Affected code:

- `scripts/diagram_geometry.py::validate_diagram_html`

An XML parse error returns the current issue list without adding a parse diagnostic. A malformed SVG with an out-of-bounds rect therefore returned no issues.

### AUD-019 — Catalog CLI is not portable and reports the wrong fixture

Affected code:

- `scripts/diagram_catalog.py::render_catalog`
- `scripts/diagram_catalog.py::_write_contact_sheet`
- `scripts/diagram_catalog.py::_render_html_template`

Evidence:

- `--output-dir /tmp/...` fails at `output_png.relative_to(ROOT)`.
- Contact-sheet reads always prepend `ROOT`, so external records are incompatible.
- Manifest always records the global default fixture, not the `--fixture` argument.
- Filled HTML is temporarily written beside the source template, causing read-only-install and concurrent-run risks.

### AUD-020 — Review manifests lack enough evidence for release decisions

Affected code:

- `scripts/drawing/review.py::write_review_bundle`

The manifest lists artifacts and an optional channel ratio, but does not record diagnostics, metrics, dimensions, content bounds, output profile, compiler version, source digest, artifact digests, baseline category, or approval state.

Impact:

- Review output is inspectable by a person but not sufficient as a deterministic release gate.

### AUD-021 — Tests cover happy-path existence better than invalid-stage behavior

Current gaps include:

- compiler/export rejection on every diagnostic layer;
- duplicate ids and unknown references for every type;
- Flowchart convergence, branch labels, terminal semantics, nested loops, parallel edges, and breadth overflow;
- Architecture candidate criteria and semantic-order preservation;
- legend and annotation bounds;
- complete accessibility order;
- external catalog paths and custom fixture identity;
- malformed SVG;
- visual-diff dimension changes;
- three-profile post-export bounds.

The current passing suite therefore demonstrates useful behavior but not the published release gates.

## 6. Positive findings

The audit also confirmed sound foundations worth preserving:

- The shared SVG renderer escapes authored element text and node ids.
- Subprocess calls use argument arrays without shell interpolation.
- ELK is isolated behind a runner and receives JSON through standard input.
- Renderer logic does not branch on Architecture node kind, focus, importance, or async semantics.
- Architecture parallel routes use a per-pair queue instead of the Flowchart overwrite pattern.
- The three-stage semantic, plan, and scene representations are inspectable and deterministic for current fixtures.
- The catalog accurately reports generator coverage as `2 / 14` instead of claiming static HTML templates are compiler-backed.
- The current templates provide strong visual parity fixtures for the migration.

## 7. Root-cause map

| Root cause | Findings | Corrective workstream |
|---|---|---|
| No shared fail-closed compiler | AUD-001, 002, 009, 010, 011 | Gate S1 |
| Partial Flowchart grammar | AUD-002, 003, 005, 012 | Gate S2 |
| Contract drift | AUD-006, 010, 017 | Gate S1 and S3 |
| Layout selection not aligned with specification | AUD-007, 008, 009, 015 | Gate S3 |
| Validation is graph- and Architecture-biased | AUD-011, 016 | V3.0 validation layers |
| Export/profile gates validate structure, not final fit | AUD-004, 013, 014, 018 | Gate S4 and V3.0 profiles |
| Review/catalog are not release-grade manifests | AUD-019, 020 | Gate S4 |
| Negative coverage is incomplete | AUD-021 | All stabilization work |

## 8. Closure policy

A finding is closed only when:

1. the production behavior is corrected;
2. a regression test reproduces the old failure and proves the new behavior;
3. the same behavior is exercised through the public CLI or build path where applicable;
4. manifest or snapshot evidence is updated;
5. documentation no longer claims behavior that is absent;
6. the full unit and build verification suite passes.

P0 and P1 findings block V3.1. P2 findings block V3.0 completion unless explicitly reclassified with written rationale and a bounded follow-up release.

## 9. Recommended first change

Implement a shared `CompilationResult` and fail-closed orchestrator for the existing Architecture and Flowchart compilers. Route every CLI render, review, metric, plan, layout, and scene command through it. This single boundary makes the later schema, grammar, layout, scene, accessibility, and profile fixes enforceable and prevents twelve new compilers from duplicating the current inconsistency.
