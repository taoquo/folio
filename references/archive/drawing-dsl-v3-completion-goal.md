# Folio Drawing DSL V3 Completion Goal

Status: complete — all V3 release gates passed  
Program plan: `drawing-dsl-v3-plan.md`  
Current audit: `drawing-dsl-v3-current-logic-audit.md`  
Final coverage: `14 / 14` generator-backed diagram types

## 0. Execution checkpoint

Checkpoint date: 2026-08-13

| Work item | State | Evidence |
|---|---|---|
| Gate S current-core stabilization | complete | Audit closure table, fail-closed CLI tests, negative grammar fixtures, full build verification |
| V3.0 shared compiler and output platform | complete | Registry metadata, type-neutral primitives, split validators, three-profile format matrix, catalog manifest 3.0 |
| V3.1 structural graph types | complete | State Machine, Swimlane, Tree, and Layer Stack registered with semantic, layout, validation, and profile coverage |
| V3.2 positional and set types | complete | Timeline, Quadrant, and Venn registered with deterministic collision and topology handling |
| V3.3 Data Viz Core | complete | Bar, Line, Donut, Candlestick, and Waterfall registered with numerical, scale, mark-id, and locale coverage |
| Gate R whole-program audit | complete | 14 / 14 catalog, 126-artifact matrix, deterministic replay, full tests and build verification |

Final generator-backed coverage is `14 / 14`. The registry, catalog fixture, generated manifest, tests, and public documentation report the same state.

## 1. Goal

Complete the Folio Drawing DSL V3 release train so all fourteen official diagram types compile from validated semantic input into deterministic, accessible, profile-safe SVG, PNG, and PDF artifacts, while preserving the constrained Folio visual language and preventing invalid plans or invalid scenes from reaching an exporter.

V3 is complete only when:

1. All confirmed P0 and P1 findings in the current-logic audit are closed with regression tests.
2. All fourteen catalog types use a registered, type-specific compiler and executable grammar.
3. Every compiler returns one shared `CompilationResult` containing the normalized input, semantic IR, plan, layout, scene, diagnostics, and metrics.
4. Compilation and export are fail-closed: any schema, semantic, grammar, numerical, canvas, primitive, or accessibility error stops artifact creation.
5. `artifact`, `embed`, and `page-preview` output profiles pass explicit bounds and typography checks in SVG, PNG, and PDF.
6. The catalog, test suite, build verification, review manifest, and documentation all report the same coverage and validation state.

This goal supersedes the earlier assumption that V3.0 can begin with output profiles alone. The current implementation requires a stabilization gate before any new diagram grammar is added.

## 2. Measurable key results

| Key result | Baseline | V3 target | Evidence |
|---|---:|---:|---|
| Generator-backed catalog coverage | 2 / 14 | 14 / 14 | Catalog manifest and compiler registry |
| Open P0 findings | 4 confirmed | 0 | Audit closure table and regression tests |
| Open P1 findings | 10 confirmed | 0 | Audit closure table and regression tests |
| Invalid inputs that can reach export | Confirmed | 0 | Negative fixture matrix |
| Output profiles per type | Implicit | 3 explicit profiles | Profile manifest |
| Profile/type artifact combinations | Partial | 126 minimum | 14 types x 3 profiles x 3 formats |
| Known A4 preview clipping | 6 types | 0 | Canvas bounds and raster edge checks |
| Scene geometry errors in valid fixtures | Dense Flowchart reproduces errors | 0 | Geometry diagnostics in CI |
| Logical SVG reading-order collisions | Present in 4 of 5 Flowchart fixtures | 0 | Accessibility regression tests |
| Perceptual dimension regressions masked | Confirmed | 0 | Diff manifest records and gates dimensions |
| Deterministic fixture replay | Partial | 100% | Repeated snapshot digest test |
| Unresolved catalog placeholders | 0 | 0 | Catalog hard gate |

The 126 artifact combinations are a minimum release matrix. Additional language, dense, empty, invalid, and adversarial fixtures do not reduce that requirement.

## 3. Scope

### In scope

- Stabilize Architecture and Flowchart before adding new type compilers.
- Add compiler registry, shared compilation envelope, normalized diagnostics, and fail-closed stage boundaries.
- Separate canvas and primitive validation from Architecture grammar.
- Add output-profile fitting and post-export validation.
- Implement State Machine, Swimlane, Tree, Layer Stack, Timeline, Quadrant, Venn, Bar, Line, Donut, Candlestick, and Waterfall grammars.
- Add Data Viz Core for scale, ticks, marks, labels, legends, and numerical validation.
- Convert the current HTML/SVG templates into parity fixtures after their compiler-backed replacements pass.
- Make catalog and review artifacts portable, deterministic, and machine-auditable.
- Preserve public Architecture, Flowchart, UML, build, and export entrypoints through compatibility adapters.

### Out of scope

- Arbitrary authored coordinates, colors, paths, font sizes, or radii.
- A universal plan schema with optional fields for every type.
- LLM-driven geometry or non-deterministic layout selection.
- Direct manipulation, animation, or an interactive editor.
- A new theme or broad template redesign.
- Sequence Diagram and UML Class migration during the fourteen-type V3 program.

## 4. Mandatory execution order

```text
Gate S  Current-core stabilization
  -> V3.0  Shared compiler and output platform
      -> V3.1  Structural graph types
          -> V3.2  Positional and set types
              -> V3.3  Data Viz Core and five chart types
                  -> Gate R  Whole-program release audit
```

No new type compiler starts before Gate S passes. A minor release cannot start its successor until its own artifact, compatibility, and documentation gates pass.

## 5. Gate S — current-core stabilization

Estimated effort: 8–12 engineering days.

### S1. Make compilation fail-closed

Deliverables:

- Add one internal compilation orchestrator for Architecture and Flowchart.
- Normalize and validate payloads before dataclass construction.
- Run semantic and type grammar validation before layout.
- Run layout, scene, accessibility, and output-profile validation before export.
- Return diagnostics instead of leaking `KeyError`, partial scenes, or silently dropped objects.
- Make `draw-plan`, `draw-layout`, `draw-scene`, `render-drawing`, `review-drawing`, and `draw-metrics` consume the same compilation result.

Acceptance:

- Missing schema versions, unknown fields, invalid vocabularies, invalid references, duplicate ids, and unknown pictograms cannot reach layout.
- Invalid layouts or scenes cannot reach SVG, PNG, or PDF export.
- CLI exit code is non-zero on any `ERROR`, and no requested artifact is left behind.

### S2. Repair the Flowchart contract

Deliverables:

- Enforce non-empty graphs, unique node and edge ids, known endpoints, one valid start, terminal semantics, focus validity, decision branch labels, convergence or explicit termination, and nested-loop depth.
- Preserve every parallel edge by id through layout and scene resolution.
- Reject or safely fit layouts that exceed canvas bounds.
- Add deterministic back-edge lanes and collision validation.
- Generate complete logical reading order, including branch-only nodes.

Acceptance:

- The audit parallel-edge fixture produces two distinct scene routes and labels.
- The audit dense fixture either produces a zero-error fitted scene or a deterministic hard error before export.
- Empty, terminal-outgoing, unlabelled-decision, duplicate-id, disconnected, deep-loop, and non-converging fixtures fail with stable diagnostic codes.

### S3. Repair Architecture layout selection and validation

Deliverables:

- Remove `spine-reversed` as a semantic mutation; candidates may vary only grammar-approved geometric choices.
- Implement the documented lexicographic criteria: geometry errors, connector overlap and edge-through-node violations, crossings, spine bends, total bends, spacing variance, and stable key.
- Validate `focus_path`, `background_nodes`, edge ids, region ids, legend vocabulary, `direction`, and `route_policy`.
- Treat canvas overflow and invalid geometry as errors, not unweighted warning counts.
- Replace silent edge dropping with an explicit compiler error.

Acceptance:

- All showcase fixtures preserve their declared primary reading path.
- Every selected candidate has zero hard geometry errors.
- Candidate metrics and selection reasons appear in the review manifest.

### S4. Repair baseline and export gates

Deliverables:

- Reject perceptual comparisons with unequal dimensions unless an explicit normalization mode is approved and recorded.
- Record source and output dimensions, content bounds, digest, profile, diagnostics, and diff method.
- Escape HTML metadata inserted by PDF export and propagate the scene language.
- Treat malformed SVG as a validation error.
- Make catalog paths portable and move temporary filled HTML into a temporary directory.

Acceptance:

- A 10 x 10 and 20 x 20 image with the same color cannot report a zero regression.
- All six known clipped catalog fixtures fail the old profile and pass only after profile fitting.
- Catalog output works inside and outside the repository root.

### Gate S exit criteria

- All audit P0 and P1 findings have a regression test and are closed.
- Architecture and Flowchart each pass valid, invalid, dense, CJK, parallel-edge, accessibility, and three-profile matrices.
- No compiler/export command bypasses the shared orchestrator.
- Full tests, `build.py --check`, `build.py --sync`, and `build.py --verify` pass.

## 6. V3.0 — shared compiler and output platform

Estimated effort after Gate S: 4–6 engineering days.

### Work packages

1. `DiagramCompilerRegistry`
   - Dispatch by normalized `kind` and schema major version.
   - Reject unknown kinds and unsupported versions before compiler construction.
   - Keep type-specific vocabulary outside shared core.

2. `CompilationResult`
   - Contain normalized input, semantic IR, plan, layout, scene, diagnostics, metrics, profile, and stable build metadata.
   - Preserve warnings and taste diagnostics without allowing errors to export.

3. Type-neutral scene primitives
   - Add rect, line, polyline, path, circle, text, group, and clip primitives.
   - Keep existing node, edge, region, annotation, and legend composites as adapters.
   - Ensure the renderer branches only on resolved primitive type.

4. Validation layers
   - `SchemaValidation`
   - `SemanticValidation`
   - `TypeValidation`
   - `CanvasValidation`
   - `PrimitiveValidation`
   - `AccessibilityValidation`
   - `TasteDiagnostics`

5. Output profiles
   - `artifact`: native 960 x 540 class output.
   - `embed`: responsive SVG without minimum-width behavior.
   - `page-preview`: explicitly fitted A4 or Letter figure.

6. Public CLI
   - Add `folio diagram-catalog`.
   - Add `--profile` to compile, render, review, and metric commands.
   - Keep legacy entrypoints as thin adapters.

### V3.0 exit criteria

- Architecture and Flowchart compile only through the registry.
- Three output profiles pass all three formats.
- Shared validators do not import `ArchitectureGrammar`.
- Catalog manifest contains bounds, diagnostics, metrics, versions, dimensions, and digests.
- No new diagram type has been added before this platform is stable.

## 7. V3.1 — structural graph types

Estimated effort: 14–20 engineering days. Coverage target: `6 / 14`.

### State Machine

- Implement state, initial, final, and history semantics.
- Validate transition ids, triggers, guards, actions, reachability, and final-state exits.
- Support bounded linear, cyclic, and branching compositions.
- Provide distinct self-loop and parallel-transition lanes.

### Swimlane

- Implement lane, step, owner, handoff, and return semantics.
- Validate exactly one owner per step and every cross-lane handoff.
- Use band layout for lanes and graph routing for steps.
- Keep returns visually distinct from forward requests.

### Tree

- Implement root, branch, leaf, and focal-subtree semantics.
- Validate one root, one parent per non-root node, acyclicity, reachability, depth, and breadth budgets.
- Add overflow policy: compact, prune with explicit reduction, or split.

### Layer Stack

- Implement ordered bands, interfaces, dependencies, and focal layer.
- Validate unique order, non-empty bands, legal adjacency, and width fitting.
- Use deterministic band layout without ELK.

### V3.1 exit criteria

- Four new compiler registrations and type schemas.
- English, Chinese, dense, invalid, and profile fixtures for each type.
- Zero clipping, node overlap, detached endpoints, and accessibility errors.
- Static templates remain visual parity references until compiler artifacts are approved.

## 8. V3.2 — positional and set types

Estimated effort: 10–14 engineering days. Coverage target: `9 / 14`.

### Timeline

- Implement ordered and scaled events, phases, focal milestone, and alternating label lanes.
- Validate monotonic order, duplicate dates, range fit, and label collision fallback.

### Quadrant

- Implement two axes, domains, points, categories, focal point, and label candidates.
- Validate finite in-domain coordinates, axis meaning, and deterministic eight-position label placement.

### Venn

- Implement bounded two-set and three-set topology.
- Validate set and intersection consistency.
- Fit intersection labels and legends without changing set semantics.

### V3.2 exit criteria

- Three new compiler registrations and type schemas.
- Positional metrics report label candidate failures, domain violations, and axis occupancy.
- All three types pass three profiles and accessibility review.

## 9. V3.3 — Data Viz Core and five chart types

Estimated effort: 18–26 engineering days. Coverage target: `14 / 14`.

### Data Viz Core

- Typed tabular input and finite-number normalization.
- Linear and categorical scales, tick generation, plot bounds, grid lines, legends, value labels, and number formatting.
- Explicit handling for missing, zero, negative, repeated, and outlier values.
- Machine-readable data summary adjacent to SVG metadata.

### Type compilers

- Bar: grouped and single-series bars, zero baseline, category and series budgets.
- Line: ordered x-domain, multiple series, missing points, endpoint labels, and crossings.
- Donut: positive finite values, total consistency, minimum visible segment policy, and deterministic arcs.
- Candlestick: OHLC invariant validation, ordered periods, scale, wick/body geometry, and volume exclusion unless explicitly added later.
- Waterfall: start/delta/subtotal/total semantics, cumulative arithmetic, bridge continuity, and negative values.

### V3.3 exit criteria

- Five new compiler registrations and type schemas.
- Numerical property tests cover invariants and degenerate inputs.
- Values shown visually equal serialized semantic values.
- All fourteen catalog entries are generator-backed.

## 10. Test program

### Required test layers

| Layer | Required coverage |
|---|---|
| Schema | Missing, unknown, wrong type, wrong version, duplicate id |
| Semantic | Unknown references, reachability, ownership, order, numerical invariants |
| Grammar | Allowed vocabulary, information budget, type notation |
| Layout | Bounds, overlap, crossings, attach points, label collisions, deterministic replay |
| Scene | Finite primitives, clips, paths, masks, text containment, logical order |
| Export | SVG, PNG, PDF for three profiles |
| Accessibility | Title, description, language, unique ids, complete reading order, data summary |
| Perceptual | Dimensions, content bounds, classified diff, approved baseline changes |
| Compatibility | Legacy Architecture, Flowchart, UML, build targets, CLI facades |
| Security | Escaping, local/remote resource policy, path portability, no shell interpolation |

### Fixture minimum per type

- One canonical English fixture.
- One canonical Chinese fixture.
- One dense but valid fixture.
- One minimal valid fixture.
- At least three invalid fixtures covering type invariants.
- One profile-specific stress fixture.
- One accessibility snapshot.

Graph types additionally require cycles, parallel edges, disconnected content, and long labels. Data types additionally require zero, negative, missing, repeated, outlier, and non-finite cases where applicable.

## 11. Release governance

### Pull request rule

Each pull request must contain one coherent change, its negative and positive tests, updated snapshots or manifest, and a short metric delta. No pull request may update a baseline only to make a failing test green without a classified visual explanation.

### Minor-release gate

- No open P0 or P1 issue in the minor scope.
- All valid fixtures compile with zero `ERROR` diagnostics.
- All invalid fixtures fail before export.
- Snapshot output is deterministic across two clean runs.
- All three profiles and three formats pass.
- Full unit and build verification passes.
- Documentation and catalog coverage match the registry.

### Rollback rule

Keep the last approved static template or legacy generator available behind a compatibility adapter until the replacement type passes one full minor release. Rollback selects the prior compiler registration; it must not fork theme or renderer code.

## 12. Tracking model

Every work item uses one state: `pending`, `in progress`, `blocked`, `verification`, or `complete`.

A work item can move to `complete` only when:

1. implementation is merged;
2. regression tests exist;
3. the relevant manifest or snapshot is updated;
4. all dependent release gates pass;
5. no documentation claims exceed implemented behavior.

The audit finding id must be included in the stabilizing change and its regression test name. New-type tasks use the release and type, for example `V3.1/TREE/semantic-parent-invariant`.

## 13. Final definition of done

V3 is complete when the registry contains fourteen production compilers, the catalog contains fourteen generator-backed entries, every valid fixture exports cleanly under all profiles, every invalid fixture stops before export, all current P0 and P1 findings are closed, compatibility entrypoints remain green, and a clean full build produces deterministic artifacts with no clipping, unresolved placeholders, geometry errors, accessibility errors, or unclassified perceptual changes.
