# Folio Drawing DSL V2 Plan

Implementation status: complete. The executable contract is covered by `tests/test_drawing_dsl_v2.py`, five Flowchart fixtures, the two V2 JSON schemas, the `artifact-flowchart-v2-demo` build target, and the CLI verification commands in `drawing-dsl.md`.

## 1. Objective

V2 turns the Architecture-first V1 compiler into a stable, authorable Drawing Core and proves that the core can support a second diagram grammar without becoming a universal graphics language.

The release has two product outcomes:

1. Architecture diagrams handle real content variation with less manual intervention.
2. Flowchart becomes the second generator-backed diagram type using the shared semantic, scene, typography, validation, and rendering layers.

V2 continues the deletion-first, constrained-vocabulary, single-accent, and 4-unit-grid principles established in V1 and informed by `diagram-design`.

## 2. Scope

### 2.1 Drawing Core 2.0

- Versioned, externally authorable DrawingPlan JSON.
- JSON Schema validation and deterministic V1-to-V2 migration.
- Type-neutral scene primitives and layout result models under `drawing/`.
- Deterministic layout candidate selection with explicit metrics.
- First-class annotations, legends, accessibility metadata, and debug artifacts.
- Automated perceptual regression in addition to semantic, plan, and scene snapshots.

### 2.2 Architecture Grammar 2.0

- Three semantic node size tiers: `compact`, `regular`, and `wide`.
- Content-driven tier selection; no arbitrary width or height.
- Region treatments: `layer-band`, `soft-boundary`, `trust-boundary`, and `phase-band`.
- First-class callouts and relationship annotations.
- A small curated pictogram vocabulary with deterministic placement.
- Better handling of parallel relationships, reverse flows, and unavoidable crossings.
- Deterministic split recommendations that can produce a reviewable multi-diagram bundle.

### 2.3 Flowchart Grammar 1.0

- Semantic steps, decisions, terminals, data operations, and labelled branches.
- Top-down and left-right reading axes.
- Structured loops and converging branches.
- Flowchart-specific information budget, grammar, validation, and fixtures.
- The same SVG, PNG, and PDF export contracts as Architecture.

## 3. Explicit Non-goals

- No freeform canvas or arbitrary coordinates.
- No user-provided colors, font sizes, stroke widths, radii, or exact paths.
- No universal grammar shared by every diagram type.
- No data-visualization migration in V2.
- No Sequence, UML Class, Swimlane, State Machine, or C4 notation implementation.
- No large icon library or automatic icon search.
- No LLM-based layout planner or opaque aesthetic score.
- No interactive editor, animation, or web-canvas runtime.
- No second visual theme; Folio remains the only production theme.

## 4. Architectural Direction

```text
Content / handwritten JSON
        |
        v
Type-specific Semantic IR
        |
        v
Type-specific DrawingPlan + shared plan envelope
        |
        v
Type Grammar -> Layout Constraints -> Layout Candidates
        |                                  |
        |                                  v
        |                         deterministic selection
        v                                  |
Shared ResolvedScene <---------------------+
        |
        +-> SVG -> PNG
        +-> SVG -> PDF
```

The shared core owns theme roles, typography, scene primitives, connector primitives, diagnostics, metrics, serialization, and export compatibility. Architecture and Flowchart own their semantic models, visual vocabulary, planning rules, layout constraints, and type-specific validation.

## 5. V2 Data Contracts

### 5.1 Versioned plan envelope

Every handwritten plan adds:

```json
{
  "schema_version": "2.0",
  "kind": "architecture",
  "composition": {},
  "hierarchy": {},
  "nodes": [],
  "edges": []
}
```

Rules:

- Missing `schema_version` is interpreted as V1.
- `migrate-drawing` upgrades V1 input deterministically.
- Unknown major versions fail with an actionable error.
- Unknown fields fail by default; a dedicated compatibility mode may preserve them.
- Schema validation happens before dataclass construction.

### 5.2 Shared envelope, type-specific payload

The shared plan envelope contains title, kind, version, canvas class, information budget, explanation, reductions, annotations, and legend intent. Node, edge, region, and composition vocabularies remain owned by each type grammar.

V2 must not introduce one global `NodePlan` whose optional fields cover every diagram type.

### 5.3 Drawing bundle

Dense content may resolve to:

```text
DrawingBundle
├── overview DrawingPlan
├── detail DrawingPlan(s)
└── navigation annotations
```

The planner may recommend a bundle automatically, but splitting is only applied when explicitly requested or selected by the caller.

## 6. Dynamic Node Sizing

V2 introduces exactly three semantic size tiers:

| Tier | Intended content | Initial geometry |
|---|---|---:|
| `compact` | short label, no metadata | 144 x 64 |
| `regular` | ordinary label and metadata | 176 x 72 |
| `wide` | long CJK/mixed title or required metadata | 224 x 80 |

Selection order:

1. Measure title, metadata, and optional pictogram reservation.
2. Select the smallest tier that fits without shrinking below the typography floor.
3. Drop optional metadata before selecting `wide` when the metadata is not semantically required.
4. Emit a warning when `wide` still cannot fit.
5. Never expose raw width or height in DrawingPlan.

The layout compiler consumes the resolved tier and still places every dimension on the 4-unit grid.

## 7. Annotation and Legend Model

Replace string annotations with a typed model:

```text
AnnotationPlan
├── target: node | edge | region | diagram
├── kind: note | constraint | risk | navigation
├── text
└── emphasis: normal | background
```

Resolved annotations use deterministic anchor preferences and leader-line routing. An annotation must not overlap a node, edge label, legend, or another annotation.

Legends become optional first-class plans rather than tuples. The planner omits a legend when the visual vocabulary is already self-explanatory.

## 8. Pictogram Subsystem

V2 permits a curated vocabulary of no more than twelve pictograms for Architecture. Initial candidates are `client`, `gateway`, `compute`, `queue`, `database`, `cache`, `storage`, `cloud`, `security`, `observability`, `network`, and `external-system`.

Rules:

- Pictograms are optional and never replace the text label.
- DrawingPlan stores a semantic pictogram id, not an SVG path.
- Grammar maps ids to built-in geometry.
- Scene resolution owns exact placement and color.
- Pictograms use the existing accent and neutral roles only.
- Unknown ids are validation errors.
- Automatic inference is restricted to unambiguous semantic roles; otherwise use no pictogram.

## 9. Layout Candidate Selection

ELK remains a backend, not the designer. V2 may produce a small deterministic candidate set by varying only grammar-approved choices such as ordering strategy, sidecar side, or routing lane.

Candidates are selected lexicographically:

1. Zero geometry errors.
2. Zero connector overlap and edge-through-node violations.
3. Minimum crossing count.
4. Minimum spine bends.
5. Minimum total bends.
6. Minimum spacing variance.
7. Stable deterministic tie-break key.

This is not an aesthetic score. Metrics remain individually visible in explain output and regression artifacts.

Candidate generation is capped at eight layouts per diagram to keep builds predictable.

## 10. Flowchart Grammar

### 10.1 Semantic vocabulary

```text
step
decision
terminal
data
subprocess
```

### 10.2 Edge vocabulary

```text
sequence-flow
conditional-flow
exception-flow
```

Conditional branches require short labels. `yes` and `no` labels use locale-aware defaults only when the source semantics explicitly identify a boolean decision.

### 10.3 Composition vocabulary

```text
linear
branching
loop
```

No `freeform` composition is allowed.

### 10.4 Information budget

- Maximum visual nodes: 12.
- Maximum decisions: 4.
- Maximum visible branch labels: 8.
- Maximum nested loop depth: 2.
- Maximum focal paths: 1.

### 10.5 Validation

Hard errors include unreachable nodes, decisions without multiple exits, branches without convergence or explicit termination, illegal loop structure, detached endpoints, overlap, and text overflow.

Taste diagnostics include excessive branch depth, long back-edges, ambiguous decision labels, repeated steps, and an unbalanced yes/no branch.

## 11. Accessibility and Output Semantics

ResolvedScene adds document title, description, language, and logical reading order. SVG output includes `<title>`, `<desc>`, stable ids, and ARIA relationships without exposing planning semantics to the renderer.

Text remains real SVG text. Pictograms and decorative region geometry are hidden from assistive technology. PNG and PDF exports retain the existing visual contract; SVG is the canonical accessible artifact.

## 12. Developer Experience

Add commands:

```bash
python3 scripts/folio.py draw-layout <fixture>
python3 scripts/folio.py draw-metrics <fixture> --format json
python3 scripts/folio.py migrate-drawing <v1-plan.json>
python3 scripts/folio.py render-drawing <plan.json> --format svg|png|pdf
python3 scripts/folio.py review-drawing <fixture> --baseline <name>
```

`review-drawing` writes semantic, plan, layout, scene, metrics, SVG, PNG, and a visual diff manifest into one review directory.

Every diagnostic adds an optional `stage`, `path`, and `suggestion` so CLI output can identify the exact input object and remediation.

## 13. Visual Regression

V2 keeps JSON snapshots and adds perceptual image comparison.

The gate is two-level:

- Structural gate: dimensions, colors, object counts, geometry errors, and metrics budgets.
- Perceptual gate: changed-pixel ratio plus a generated difference image.

Perceptual changes never auto-update baselines. A baseline update requires an explicit command and a review manifest describing whether the change is semantic, layout, typography, connector, theme, or renderer related.

## 14. Delivery Phases

### Phase 0 — Freeze V1

- Tag the V1 schema and fixture snapshots.
- Record metrics for Architecture, Chinese, and dense fixtures.
- Add compatibility tests for every public facade.

Exit: V1 plans and APIs have immutable compatibility fixtures.

### Phase 1 — Core extraction

- Move `LayoutResult`, boxes, and edges into `drawing/layout/models.py`.
- Remove Drawing Core dependencies on legacy diagram modules.
- Separate shared scene primitives from Architecture-specific scene composition.

Exit: `scripts/drawing/` imports no Architecture legacy spec or renderer module.

### Phase 2 — Versioned authoring contract

- Add `schema_version`.
- Add JSON Schemas and V1 migration.
- Add schema and migration CLI commands.

Exit: handwritten V1 and V2 plans produce equivalent scenes.

### Phase 3 — Typography and node tiers

- Implement `compact`, `regular`, and `wide`.
- Add required/optional metadata semantics.
- Expand CJK, mixed-script, and technical-token fixtures.

Exit: all text-fit fixtures resolve without overflow or arbitrary sizing.

### Phase 4 — Architecture 2.0 semantics

- Add typed annotations and legend plans.
- Add trust and phase regions.
- Add curated pictograms.
- Add relationship direction and parallel-edge cases.

Exit: all new visual vocabulary has executable grammar, validation, and scene snapshots.

### Phase 5 — Layout candidates and routing

- Implement capped deterministic candidate generation.
- Add lexicographic selection and explain output.
- Improve parallel routes, reverse flows, label placement, and crossing resolution.

Exit: Architecture regression fixtures have no geometry errors, connector overlap, or edge-through-node violations.

### Phase 6 — Drawing bundles

- Add split recommendations with subsystem evidence.
- Add overview/detail bundle generation behind explicit opt-in.
- Add navigation annotations and bundle export.

Exit: a 12–18-node fixture resolves into valid overview and detail diagrams without exceeding per-diagram budgets.

### Phase 7 — Flowchart vertical slice

- Add Flowchart Semantic IR, DrawingPlan, grammar, planner, layout, resolver, and validators.
- Migrate the generator-backed flowchart artifact path.
- Add English, Chinese, branch, loop, and dense fixtures.

Exit: Flowchart uses the shared renderer and export paths without Architecture conditionals in Drawing Core.

### Phase 8 — Accessibility and regression tooling

- Add SVG metadata and reading order.
- Add perceptual comparison and review manifests.
- Add dual-backend build tests for both diagram types.

Exit: all release fixtures pass structural, accessibility, SVG, PNG, PDF, and perceptual gates.

### Phase 9 — Documentation and migration

- Update skill routing and authoring documentation.
- Publish V1-to-V2 migration examples.
- Replace coordinate-oriented Flowchart guidance with grammar-oriented guidance.
- Produce controlled before/after contact sheets.

Exit: public docs contain no conflicting source of truth.

## 15. Recommended PR Sequence

1. `docs: freeze drawing DSL v1 contracts`
2. `refactor: move layout primitives into drawing core`
3. `feat: version and validate drawing plans`
4. `feat: migrate v1 drawing plans`
5. `feat: add semantic node size tiers`
6. `feat: add typed annotations and legends`
7. `feat: add architecture region treatments`
8. `feat: add curated architecture pictograms`
9. `feat: select deterministic layout candidates`
10. `feat: generate reviewable drawing bundles`
11. `feat: introduce flowchart semantic and drawing IR`
12. `feat: compile flowcharts into resolved scenes`
13. `test: add drawing perceptual regression`
14. `feat: add accessible SVG scene metadata`
15. `docs: publish drawing DSL v2 migration guide`

Every PR must keep all public Architecture and UML facades working. Any visual change requires a before/after artifact and a metric delta explanation.

## 16. Release Gates

### Architecture

- V1 plans migrate without semantic loss.
- Existing five fixtures retain zero geometry errors and zero text overflow.
- The three showcase fixtures retain zero connector overlap and zero crossings.
- Dynamic tiers are selected deterministically.
- Pictograms and annotations do not increase focal-object count unexpectedly.
- A dense split fixture produces a valid bundle when explicitly requested.

### Flowchart

- At least five fixtures cover linear, branching, loop, Chinese, and dense cases.
- Every decision has valid exits and readable branch labels.
- No unreachable visual nodes.
- Zero node overlap, edge-through-node violations, text overflow, or detached endpoints.
- SVG, PNG, and PDF artifacts build successfully.

### Core

- DrawingPlan schema and migration tests pass.
- Renderer remains free of semantic branching.
- Type-specific grammar does not leak into shared core.
- All geometry and text anchors remain on the 4-unit grid.
- SVG contains title, description, language, and reading order.
- Perceptual changes require explicit baseline approval.
- Full Folio `build.py --check`, `--sync`, and `--verify` pass.

## 17. Success Metrics

V2 is successful when:

- At least 95% of valid Architecture and Flowchart fixtures compile without manual overrides.
- All release fixtures have zero geometry errors and zero text overflow.
- Showcase diagrams have zero connector overlap and zero crossings.
- Median primary-path bends do not exceed two.
- V1-to-V2 migration changes no semantic node, edge, focus, or region membership.
- A failing diagram can be localized to semantic, plan, layout, scene, or renderer stage from one review bundle.
- Adding Flowchart requires no Architecture-specific branch in the shared SVG renderer.

## 18. Deferred V3 Candidates

- Sequence grammar.
- State Machine grammar.
- Swimlane grammar.
- UML migration to its own semantic and notation grammar.
- Data Visualization Core.
- Additional themes.
- Interactive authoring and animation.
