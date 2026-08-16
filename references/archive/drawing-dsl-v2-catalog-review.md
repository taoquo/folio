# Drawing DSL V2 Catalog Review

Status: completed baseline review  
Fixture: `references/fixtures/diagram-catalog.json`  
Renderer: `scripts/diagram_catalog.py`  
Catalog: fourteen official Folio diagram types

## 1. Executive result

All fourteen catalog types can be rendered into review PNGs, but only Architecture and Flowchart currently pass through the generator-backed Drawing DSL V2 compiler. The other twelve images are filled HTML/SVG template baselines.

Current executable coverage is therefore `2 / 14`, or `14.3%` of the official catalog. This number measures generator-backed type coverage, not visual quality.

The review exposed two different quality profiles:

- Drawing DSL V2 outputs preserve readable hierarchy, stable focal emphasis, real text, and complete connector geometry.
- Static templates preserve the Folio visual language, but wide structural diagrams are not safe under the current A4 PDF preview path because their CSS minimum widths exceed the printable viewport.

## 2. Generated artifacts

- Complete contact sheet: historical V2 snapshot, removed. Current sheet: `assets/demos/drawing-dsl-all-types.png`
- Generator-backed contact sheet: historical V2 snapshot, removed. Current sheet: `assets/demos/drawing-dsl-supported-types.png`
- Individual PNGs: `assets/diagrams/generated/catalog/png/`
- Machine-readable coverage manifest: `assets/diagrams/generated/catalog/manifest.json`

The catalog script substitutes real review content for every HTML placeholder before rendering. An unresolved placeholder is a hard failure.

## 3. Type-by-type review

| Type | Current path | Result | Main finding | V3 action |
|---|---|---|---|---|
| Architecture | Drawing DSL V2 | Pass | Strong hierarchy and focal path; raw artifact is clear, but A4 showcase fit wastes vertical space | Add output-profile-aware figure fitting |
| Flowchart | Drawing DSL V2 | Pass | Branching is legible and connector semantics read correctly | Expand regression matrix for linear, loop, dense, and CJK fixtures |
| Quadrant | HTML/SVG | Warning | Visual vocabulary works; minimum-width behavior presses the right edge in PDF | Add positional grammar and label collision resolution |
| Bar Chart | HTML/SVG | Warning | Marks and values are readable; data and category geometry remain hand-authored | Move values, scale, ticks, and labels into Data Viz Core |
| Line Chart | HTML/SVG | Pass baseline | The strongest static data baseline; series hierarchy and endpoint labels read well | Use as visual parity fixture for Data Viz Core |
| Donut Chart | HTML/SVG | Pass baseline | Clear focal segment and external legend; geometry is still manually encoded | Add proportion validation and deterministic arc generation |
| State Machine | HTML/SVG | Fail export | Terminal content is clipped on the right in A4 PNG/PDF output | First structural grammar after export contract repair |
| Timeline | HTML/SVG | Fail export | Final milestone is clipped on the right | Add timeline scale and alternating-label collision policy |
| Swimlane | HTML/SVG | Fail export | Later steps and return path are clipped on the right | Add lane ownership, handoff routing, and lane-bound validation |
| Tree | HTML/SVG | Fail export | Root/branch layout is structurally clear, but the focal subtree is clipped | Add hierarchy grammar with bounded breadth and depth |
| Layer Stack | HTML/SVG | Fail export | Band vocabulary is good; layer bars extend beyond the printable canvas | Add deterministic band layout without ELK |
| Venn | HTML/SVG | Fail export | Overlap semantics are readable, but the second set and legend press past the page | Add fixed two/three-set topology and intersection text fitting |
| Candlestick | HTML/SVG | Pass baseline | Price marks, wick/body contrast, and labels remain legible | Use as the advanced Data Viz parity fixture |
| Waterfall | HTML/SVG | Warning | Bridge logic reads, but wide labels and edge bars have little export tolerance | Add cumulative arithmetic validation and label-fit policy |

## 4. Systemic findings

### 4.1 Export width is the first blocker

Several structural templates declare `svg { min-width: 780px–860px; }` while the default A4 printable content width is smaller after margins. WeasyPrint correctly creates a page, but page count does not detect horizontal clipping. A one-page build can therefore be structurally successful and visually invalid.

V3 needs three explicit output profiles:

- `artifact`: native scene aspect ratio, normally 960 x 540.
- `embed`: responsive SVG with no CSS minimum width.
- `page-preview`: a fitted figure inside an A4 or Letter frame.

The build must validate content bounds after the output profile is applied.

### 4.2 Current scene primitives are graph-biased

`ResolvedScene` currently models nodes, edges, regions, annotations, and legends. This is sufficient for Architecture and Flowchart, but it cannot represent axes, ticks, bars, points, circles, arcs, candles, or stacked bands without abusing graph nodes.

V3 must add type-neutral resolved primitives. Those primitives belong only in `ResolvedScene`; agent-authored plans must still not expose coordinates, colors, exact paths, or pixel dimensions.

### 4.3 Validation is not yet catalog-neutral

`validate_scene_geometry` defaults to `ArchitectureGrammar`, and metrics assume a graph with nodes, edges, and a spine. Data and positional diagrams require shared canvas/text checks plus type-specific numerical and notation checks.

### 4.4 The static catalog is valuable as a parity set

The twelve templates should not be deleted at the start of migration. Their focal hierarchy, palette, typography, captions, and information budgets are controlled visual references. Each grammar should replace its template only after semantic, scene, artifact, and perceptual parity gates pass.

## 5. Immediate acceptance baseline

The V3 program starts from these measurable facts:

- Fourteen catalog entries exist and resolve all placeholders.
- Two entries are generator-backed.
- Twelve entries are explicit migration baselines.
- All fourteen produce a PNG.
- Six wide structural/positional baselines visibly clip or press outside the A4 export viewport.
- Architecture and Flowchart pass the existing semantic and geometry unit suites.

The detailed delivery sequence is defined in `references/drawing-dsl-v3-plan.md`.
