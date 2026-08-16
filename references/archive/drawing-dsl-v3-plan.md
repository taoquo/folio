# Folio Drawing DSL V3 Plan

Status: complete — Gate S, V3.0, V3.1, V3.2, V3.3, and Gate R passed  
Input baseline: `drawing-dsl-v2-catalog-review.md`  
Program objective: migrate the complete fourteen-type Folio diagram catalog to executable, testable type grammars without turning DrawingPlan into a universal graphics language.

Execution contract: `drawing-dsl-v3-completion-goal.md`  
Current-core audit: `drawing-dsl-v3-current-logic-audit.md`

Implementation checkpoint: 2026-08-13

- Gate S is complete. All twenty-one audit findings have production fixes and regression coverage.
- V3.0 is complete. All public compilation paths use the shared registry, `CompilationResult`, fail-closed validation layers, three output profiles, and portable review manifests.
- V3.1 is complete. State Machine, Swimlane, Tree, and Layer Stack use type-owned structural grammars.
- V3.2 is complete. Timeline, Quadrant, and Venn use deterministic positional and fixed-topology grammars.
- V3.3 is complete. Bar, Line, Donut, Candlestick, and Waterfall use shared data contracts, scales, formatting, stable mark ids, and numerical validation.
- Gate R is complete. Registry and catalog coverage are `14 / 14`; the 126-artifact profile matrix and full build verification pass.

The current-core stabilization gate in the execution contract is a mandatory precondition for this release train. It closes the confirmed fail-open compilation, Flowchart semantic loss, invalid-layout export, and review-gate defects before any new type compiler begins.

## 1. Product outcome

V3 is a staged catalog-completion program, not one oversized compiler rewrite.

At the end of the V3 minor series:

1. Every official diagram type accepts structured semantic input.
2. Every type compiles through a type-specific plan and grammar into shared resolved scene primitives.
3. Every type exports SVG, PNG, and PDF without clipping.
4. Every diagram has semantic, numerical, geometry, accessibility, and perceptual regression coverage appropriate to its notation.
5. The hand-authored HTML/SVG templates become parity references and examples rather than production sources of truth.

The program expands generator-backed catalog coverage from `2 / 14` to `14 / 14` through four independently releasable minors.

## 2. Release train

| Release | Scope | Coverage after release | Relative effort |
|---|---|---:|---:|
| V3.0 | Output profiles, catalog QA, compiler registry, scene/validator extraction | 2 / 14 | 4–6 engineering days |
| V3.1 | State Machine, Swimlane, Tree, Layer Stack | 6 / 14 | 14–20 engineering days |
| V3.2 | Timeline, Quadrant, Venn | 9 / 14 | 10–14 engineering days |
| V3.3 | Bar, Line, Donut, Candlestick, Waterfall through Data Viz Core | 14 / 14 | 18–26 engineering days |

The estimate assumes one engineer familiar with the current codebase, existing dependencies, and one focused visual-review round per minor. It excludes unrelated template or website work.

## 3. Non-goals

- No arbitrary coordinates, dimensions, colors, font sizes, radii, or SVG paths in authored plans.
- No single global node or mark schema with optional fields for every diagram type.
- No LLM-driven layout solver.
- No automatic icon search or expanded pictogram marketplace.
- No animation, interactive canvas, or direct-manipulation editor.
- No new visual theme.
- No Sequence diagram until the existing fourteen-type catalog reaches executable coverage.
- No UML Class migration inside the fourteen-type program; UML retains its notation-specific legacy generator and receives only compatibility tests.

## 4. Architectural changes

### 4.1 Compiler registry

Replace CLI branching such as `if kind == flowchart` with a registry:

```text
DiagramCompilerRegistry
├── architecture -> ArchitectureCompiler
├── flowchart    -> FlowchartCompiler
├── state        -> StateMachineCompiler
├── swimlane     -> SwimlaneCompiler
├── tree         -> TreeCompiler
└── ...
```

Each compiler owns:

- payload/schema validation;
- semantic IR construction;
- planning;
- layout;
- type-specific validation;
- scene resolution;
- metrics adapters.

The registry returns one shared compilation envelope:

```text
CompilationResult
├── kind
├── semantic
├── plan
├── layout
├── scene
├── diagnostics
└── metrics
```

CLI commands consume `CompilationResult` without knowing the type vocabulary.

### 4.2 Type-neutral resolved primitives

Keep authored plans semantic. Expand only `ResolvedScene` with renderer-ready primitives:

```text
SceneRect
SceneLine
ScenePolyline
ScenePath
SceneCircle
SceneText
SceneGroup
SceneClip
```

Existing `SceneNode`, `SceneEdge`, `SceneRegion`, and `SceneLegend` may remain convenience composites, but they resolve into the same primitive layer before SVG serialization.

The SVG renderer branches only on resolved primitive type. It must never branch on state meaning, lane ownership, time scale, data series, or focal semantics.

### 4.3 Validation layers

Split current validation into four levels:

1. `CanvasValidation`: bounds, finite geometry, 4-unit anchors where required, text containment, output-profile fit.
2. `PrimitiveValidation`: illegal paths, detached arrows, invalid arcs, label masks, clip references.
3. `TypeValidation`: notation and numerical invariants owned by each grammar.
4. `TasteDiagnostics`: density, imbalance, label pressure, focal clarity, and reading-path concerns.

`CanvasValidation` must not import `ArchitectureGrammar`.

### 4.4 Layout backends

V3 keeps multiple deterministic layout strategies behind a small interface:

| Backend | Types | Responsibility |
|---|---|---|
| ELK graph layout | Architecture, Flowchart, State Machine, Swimlane, Tree | constrained graph placement and orthogonal routing assistance |
| Band layout | Layer Stack, Swimlane lanes | ordered lane/band geometry |
| Axis layout | Timeline, Quadrant, Bar, Line, Candlestick, Waterfall | scales, ticks, plot region, label lanes |
| Fixed topology | Venn, Donut | constrained circle/arc geometry for two or three sets or bounded segments |

ELK remains a backend, not the source of notation or design decisions.

### 4.5 Output profiles

Every compile/export command accepts one of three profiles:

```text
artifact      native diagram aspect ratio
embed         responsive SVG figure
page-preview  fitted A4/Letter review page
```

Rules:

- `artifact` preserves the scene viewBox and contains no document frame.
- `embed` has no CSS `min-width` and scales inside its host figure.
- `page-preview` computes a fit transform and verifies the fitted bounds.
- Output profiles never modify semantic layout to make clipping disappear.
- A profile that cannot preserve the typography floor returns an error or an explicit split recommendation.

## 5. V3.0 — Output and core readiness

### 5.1 Deliverables

- Land `diagram-catalog.json`, `diagram_catalog.py`, both contact sheets, and the coverage manifest.
- Add `folio diagram-catalog` as the public CLI facade.
- Add `--profile artifact|embed|page-preview` to rendering and review commands.
- Add a post-export bounds check for SVG and PDF preview canvases.
- Remove CSS minimum-width dependence from generated preview wrappers.
- Add the compiler registry and `CompilationResult`.
- Extract shared canvas validators from Architecture-specific geometry validation.
- Add resolved primitive serialization without changing Architecture or Flowchart output.

### 5.2 Tests

- Catalog membership exactly matches `DIAGRAM_TARGETS`.
- Every catalog placeholder resolves.
- Every preview has non-empty pixels inside all four page bounds.
- A deliberately oversized SVG fails with an actionable `ERROR`.
- Architecture and Flowchart snapshots remain byte-stable unless an approved output-profile fixture changes.
- `artifact`, `embed`, and `page-preview` produce the expected dimensions.

### 5.3 Exit gate

All fourteen baselines render without horizontal clipping in `page-preview`, even though only two are generator-backed. This makes later perceptual comparisons trustworthy.

## 6. V3.1 — Structural grammar pack

### 6.1 State Machine grammar

Semantic vocabulary:

```text
state
initial
final
choice
history (deferred unless a fixture requires it)
transition
guard
event
action
```

Plan vocabulary:

```text
composition: linear | cyclic | branching
state emphasis: focal | normal | background
transition channel: normal | exceptional | reset
label policy: event | guard | event-and-guard
```

Initial information budget:

- maximum 9 visual states;
- maximum 14 transitions;
- maximum 2 choices;
- maximum 1 focal state or focal path;
- maximum 6 visible transition labels;
- maximum cycle nesting depth 2.

Hard validation:

- exactly one initial entry unless the diagram is an explicit submachine;
- at least one reachable final state or an explicit persistent-state declaration;
- no unreachable state;
- transition endpoints attach to state boundaries;
- guards from the same choice are non-duplicated;
- final states have no ordinary outgoing transition;
- zero node overlap, edge-through-state, or export clipping.

Parity fixture: current `state-machine.html` lifecycle.

### 6.2 Swimlane grammar

Semantic vocabulary:

```text
actor / lane
step
decision
handoff
message
data access
start / end
```

Plan vocabulary:

```text
flow axis: left-right | top-down
lane order
lane emphasis
handoff channel: request | response | async
step archetype: action | decision | data | terminal
```

Initial information budget:

- 2–5 lanes;
- maximum 12 steps;
- maximum 8 lane handoffs;
- maximum 3 decisions;
- maximum 1 focal lane or focal path.

Hard validation:

- every step belongs to exactly one lane;
- no node crosses a lane boundary;
- handoff endpoints terminate inside their owner lanes;
- one connected start unless explicitly declared as parallel starts;
- no unreachable step;
- return paths remain visually distinct from request paths.

Parity fixture: current `swimlane.html` request flow.

### 6.3 Tree grammar

Semantic vocabulary:

```text
root
branch
leaf
parent-child
focal-subtree
```

Rules:

- one root;
- every non-root node has exactly one parent;
- no cycle;
- maximum depth 4;
- maximum 5 children per visible branch;
- maximum 15 nodes before split recommendation;
- sibling ordering is stable and authorable without coordinates.

The planner selects a focal subtree, not individually colored focal leaves.

Parity fixture: current `tree.html` hierarchy.

### 6.4 Layer Stack grammar

Semantic vocabulary:

```text
layer
layer responsibility
dependency direction
request direction
response direction
```

Rules:

- 3–7 ordered layers;
- exactly one optional focal layer;
- no ELK dependency;
- band heights come from compact/regular content tiers;
- request and response directions are semantic channels, never arbitrary arrows;
- long layer descriptions drop metadata before shrinking text.

Parity fixture: current `layer-stack.html` compiler stack.

### 6.5 V3.1 exit gate

- Coverage reaches `6 / 14`.
- Four types support semantic, plan, layout, scene, SVG, PNG, and PDF snapshots.
- CJK and mixed-script fixtures exist for State Machine and Swimlane.
- All structural fixtures have zero overlap, detached endpoint, text overflow, and export clipping errors.
- Static templates remain visually available until their generator parity manifests are approved.

## 7. V3.2 — Positional grammar pack

### 7.1 Timeline

Input uses ordered events with ISO date, display label, description, and importance. The author may choose `ordinal` or `temporal` scale intent, but cannot set x positions.

Rules:

- 3–10 milestones;
- stable chronological ordering;
- alternating label lanes with collision detection;
- one focal milestone;
- date labels remain real text;
- events outside the visible range are an error, never silently clipped.

### 7.2 Quadrant

Input uses two named axes and normalized semantic values or domain values with declared scales.

Rules:

- 4–12 items;
- one preferred region and at most two focal items;
- deterministic point-label placement in eight candidate positions;
- overlap fallback to numbered keys plus an external legend;
- axes use meaningful low/high labels rather than raw geometry.

### 7.3 Venn

Input uses two or three sets, exclusive items, intersections, and narrative focus.

Rules:

- only two-set and three-set canonical topology;
- no arbitrary circle center or radius in plans;
- intersection text has first claim on overlap space;
- overflow moves examples to an external legend before font reduction;
- empty intersections are explicit and visually quiet.

### 7.4 V3.2 exit gate

- Coverage reaches `9 / 14`.
- Timeline labels never collide or leave the canvas.
- Quadrant points and labels have deterministic positions and zero unresolved collisions.
- Venn membership is preserved exactly between semantic input and visible labels/legend.

## 8. V3.3 — Data Visualization Core

### 8.1 Shared data contracts

```text
Dataset
├── dimensions
├── measures
├── series
├── units
├── locale
├── source note
└── missing-value policy

ScalePlan
├── domain policy
├── zero policy
├── tick policy
├── label format
└── comparison baseline
```

Plans express data intent, not plot coordinates.

Shared numerical rules:

- reject NaN and infinite values;
- preserve source precision while formatting display precision separately;
- deterministic “nice” tick generation;
- locale-aware thousands, percentages, currency, and dates;
- zero baseline required for bars unless an explicit indexed comparison grammar applies;
- missing values are gap, zero, carry-forward, or error only when explicitly declared;
- every visible mark maps back to a source value and stable id.

### 8.2 Bar grammar

- maximum 8 categories and 3 series;
- grouped and single-series only in V3;
- category order is input, value, or explicit semantic order;
- data labels drop before bars become unreadably narrow;
- negative values use the same single-accent palette and a zero line.

### 8.3 Line grammar

- maximum 12 points and 3 lines;
- time and ordinal x scales;
- endpoint labels preferred over a legend when unambiguous;
- gaps remain gaps unless the missing-value policy says otherwise;
- focal series uses the accent; secondary series use warm neutrals and dash variation.

### 8.4 Donut grammar

- 2–6 positive segments;
- total must be positive;
- optional percent-total validation with configurable tolerance;
- segments order deterministically from the top;
- values below the label threshold move to the legend;
- use Bar instead when segment count exceeds six.

### 8.5 Candlestick grammar

- maximum 30 periods;
- validate `low <= open/close <= high`;
- ascending time order;
- deterministic price domain padding and tick scale;
- up/down semantics use Folio brand/stone, never green/red market conventions;
- missing periods appear as spacing gaps, not synthetic candles.

### 8.6 Waterfall grammar

- maximum 8 contributions plus start/end totals;
- cumulative arithmetic is compiler-calculated;
- displayed end total must match the calculated total within declared rounding tolerance;
- increases, decreases, and totals use semantic theme roles;
- connector levels derive from cumulative values.

### 8.7 V3.3 exit gate

- Coverage reaches `14 / 14`.
- Every plotted value round-trips to a stable source id.
- Scale and tick snapshots are deterministic.
- All numerical invariants have failing fixtures.
- SVG, PNG, and PDF artifacts contain the same values and labels.
- Perceptual parity is approved against the five static data templates.

## 9. Fixture matrix

Every new grammar ships at least these fixtures:

| Fixture class | Purpose |
|---|---|
| canonical | closest semantic match to the current HTML template |
| compact | minimum useful content |
| dense | exact information-budget boundary |
| overflow | one item beyond the budget, expecting split/reduction/error |
| CJK | Chinese labels and punctuation |
| mixed | CJK + English technical tokens or dates |
| invalid | notation or numerical invariant failure |
| export | artifact, embed, and page-preview dimensions |

Data types additionally need zero, negative, missing, extreme-range, and rounding fixtures when those values are legal.

## 10. Metrics

Shared metrics:

- content bounds versus canvas;
- text overflow and label collision count;
- focal object count;
- unresolved placeholders;
- visible object count;
- artifact dimensions;
- changed-pixel ratio against approved baseline.

Graph metrics:

- nodes, edges, crossings, bends, shared attach points, edge-through-node violations, unreachable objects.

Positional metrics:

- label candidate failures, axis occupancy, out-of-domain values, legend fallback count.

Data metrics:

- source values, visible marks, omitted labels, scale domain, tick count, arithmetic delta, missing-value count.

There remains no aggregate aesthetic score.

## 11. Compatibility and migration

1. Keep all existing `assets/diagrams/*.html` files through V3.3 as parity fixtures and manual escape hatches.
2. Add generator-backed artifact targets alongside existing diagram targets.
3. Route new CLI input to the compiler registry by `kind`.
4. Switch public documentation to the generator only after a type's release gate passes.
5. Mark the HTML template as legacy after one minor release with no compatibility regression.
6. Remove coordinate-editing guidance from `diagrams.md` only after all five data grammars are executable.

No migration may silently alter labels, data values, set membership, state reachability, lane ownership, or hierarchy membership.

## 12. Recommended PR sequence

1. `test: add complete diagram catalog review fixture`
2. `feat: add diagram output profiles and bounds validation`
3. `refactor: introduce compiler registry and compilation result`
4. `refactor: extract type-neutral resolved scene primitives`
5. `refactor: split shared canvas validation from architecture validation`
6. `feat: add state machine semantic and plan contracts`
7. `feat: compile state machines into resolved scenes`
8. `feat: add swimlane semantic ownership and lane layout`
9. `feat: add swimlane handoff routing and validation`
10. `feat: add tree hierarchy grammar`
11. `feat: add layer stack band grammar`
12. `test: approve v3.1 structural parity manifests`
13. `feat: add shared axis and label-lane primitives`
14. `feat: add timeline grammar`
15. `feat: add quadrant grammar and collision resolver`
16. `feat: add venn fixed-topology grammar`
17. `test: approve v3.2 positional parity manifests`
18. `feat: add dataset and scale contracts`
19. `feat: add bar and line grammars`
20. `feat: add donut arc grammar`
21. `feat: add candlestick financial mark grammar`
22. `feat: add waterfall cumulative grammar`
23. `test: approve v3.3 data parity manifests`
24. `docs: switch the fourteen-type catalog to executable examples`

Every PR must keep Architecture, Flowchart, and UML public facades working.

## 13. Release gates

### Core

- Renderer code contains no diagram-semantic branches.
- Shared validators import no type grammar.
- Plans expose no pixel or palette controls.
- Three output profiles pass bounds and typography-floor checks.
- Compiler registry dispatch is deterministic and schema-version-aware.

### Visual

- Zero content clipping in SVG, PNG, and PDF.
- One accent and at most two focal semantic objects per diagram unless the type budget is stricter.
- Text stays real text in SVG.
- Captions and focal color make the same claim.
- Perceptual baseline changes require an explicit manifest category and review.

### Accessibility

- SVG title, description, language, stable ids, and logical reading order.
- Decorative guides, grids, and pictograms are hidden from assistive technology.
- Data charts expose a machine-readable value summary in SVG metadata or an adjacent artifact manifest.

### Build

- Full unit suite passes.
- `build.py --check`, `--sync`, and `--verify` pass.
- `diagram_catalog.py` produces fourteen individual PNGs, two contact sheets, and a complete manifest.
- No unresolved placeholders remain in release artifacts.

## 14. Completion record

The full release train is implemented. Gate S and V3.0 established shared compilation, fail-closed CLI routing, explicit output profiles, type-neutral validation, and portable release evidence. V3.1–V3.3 added the twelve remaining type compilers without introducing semantic branches in the renderer.

Release evidence includes the published V3 payload schema, canonical and language fixtures, compact/dense/overflow/invalid test generators, deterministic replay, numerical edge cases, path-bounds validation, a 14 x 3 x 3 artifact matrix, fourteen page-preview catalog PNGs, two V3 contact sheets, and a manifest reporting `14 / 14` generator coverage. Static HTML/SVG templates remain parity fixtures and manual rollback references.
