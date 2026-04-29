# Diagram Artifacts Design

**Goal:** Add a low-intrusion diagram artifact pipeline to Folio so standalone technical diagrams can be generated in native Folio style and reused unchanged inside documents and slides.

## Decision

Folio will **not** add a ninth document type for diagrams.

Instead, Folio will add a parallel capability layer named **diagram artifacts**.

First version scope:

- `architecture`
- `uml-class`

Both artifact kinds share one production chain:

- `JSON spec -> SVG -> PNG -> PDF`

`SVG` is the single source of truth.

- `PNG` exists for preview, README, and external sharing
- `PDF` exists for standalone delivery and print
- document embedding and slide reuse must consume the same generated `SVG`, not a second rendering path

## Why This Shape

This structure matches Folio better than a new document type for four reasons:

1. A diagram is not a paginated editorial template. It is a reusable visual asset.
2. The same generated diagram must work in three contexts: standalone output, embedded figure, and slide visual.
3. Folio's existing document-type system is tied to page-count contracts and template semantics that do not fit diagram assets.
4. Keeping diagrams as artifacts avoids spreading diagram-specific logic across every document template.

## Scope

### In scope

- Add a standalone artifact pipeline for diagram generation
- Support `architecture` diagrams in native Folio style
- Support `uml-class` diagrams in native Folio style
- Produce `SVG + PNG + PDF` for standalone output
- Allow generated `SVG` to be embedded into HTML documents
- Allow generated `SVG` to be reused inside slides
- Add routing rules so requests for standalone diagrams use the artifact pipeline
- Add verification rules for syntax, export, and style conformance

### Out of scope

- No expansion to all 14 existing diagram families in this task
- No adoption of external visual styles, dark themes, blueprint styles, or brand-green styles
- No natural-language-to-spec parser in v1
- No advanced automatic layout optimization beyond the declared layout families
- No package / namespace grouping for UML class diagrams in v1
- No note / comment boxes for UML class diagrams in v1

## Product Behavior

### 1. Standalone output

When the user asks for a standalone architecture diagram or UML class diagram, Folio should generate:

- one `SVG`
- one `PNG`
- one single-page `PDF`

The `PDF` is a wrapper export of the generated `SVG`. It is not a document-template output and does not participate in the page-count contracts for the eight document types.

### 2. Embedded output

When the user asks for a diagram inside a long-doc, one-pager, portfolio, equity report, or other HTML document:

- generate the same `SVG`
- embed that `SVG` into the host document `<figure>`
- keep caption writing in the host template flow

The embedded path must not redraw the diagram with a second implementation.

### 3. Slide reuse

When the user asks for a diagram inside slides:

- generate the same `SVG`
- place the rendered artifact into the slide composition area

Slides should not maintain a separate architecture-drawing implementation.

## Artifact Kinds

### Architecture

`architecture` is for common technical system diagrams, not generic concept maps.

Supported layout families in v1:

- `horizontal-layers`
- `vertical-stack`
- `hub-and-spoke`

Expected use cases:

- web / app delivery stack
- microservices
- AI / agent system architecture
- data platform architecture
- internal platform / enterprise service topology

### UML Class

`uml-class` is a separate artifact kind, not an architecture sub-variant.

Supported semantic elements in v1:

- `class`
- `interface`
- `enum`
- attributes
- methods
- inheritance
- association
- aggregation
- composition

Not supported in v1:

- package grouping
- note callouts
- generics-heavy rendering rules
- dense multi-namespace layout solving

## Style Rules

All generated diagrams must stay inside the current Folio visual system.

### Required style constraints

- warm parchment-led canvas
- one accent system only: cinnabar-coral
- warm neutral support colors only
- serif-led editorial feel overall
- mono reserved for technical micro-labels only
- no second design system

### Explicit exclusions

- no dark mode
- no neon
- no blueprint cyan
- no glassmorphism
- no OpenAI green accent system
- no multi-accent node taxonomy

### Token source

Generated diagrams must map to the same Folio token vocabulary already documented in `references/diagrams.md` and existing diagram templates.

The renderer should consume canonical token values instead of duplicating ad hoc color constants across files.

## Rendering Principles

### SVG as truth

All geometry is authored once in generated `SVG`.

From that truth:

- `PNG` is exported with `rsvg-convert`
- `PDF` is exported through a minimal single-page HTML wrapper that embeds the same `SVG`

### Arrow strategy

Do not make `marker orient="auto"` the primary arrow strategy.

Folio already documents WeasyPrint instability around auto-oriented markers. The diagram renderer should prefer explicit path-based arrowheads or another PDF-stable directional strategy from the start.

### Layout discipline

Generated diagrams must preserve Folio's anti-slop rules:

- bounded node-count and density
- discrete node size tiers
- exact edge anchoring
- warm palette only
- one focal region, maximum two
- labels that support editorial reading, not UI-like chrome

## Spec Model

### Common envelope

Both diagram kinds should share a top-level artifact envelope:

- `kind`
- `title`
- `subtitle`
- `caption`
- `layout`
- `width`
- `height`
- `legend`
- `focus`
- `output_name`

This keeps build, export, and routing logic generic.

### Architecture spec

The `architecture` spec should include:

- `layout`
- `layers`
- `nodes`
- `edges`
- `groups`
- `legend`
- `focus_node`

Node semantics in v1 should be restrained and map directly to Folio's existing architecture vocabulary, such as:

- `external`
- `service`
- `store`
- `cloud`

Edge semantics in v1 should stay compact:

- `primary`
- `secondary`
- `async`

### UML class spec

The `uml-class` spec should include:

- `types`
- `relationships`
- `focus_type`

`packages` are explicitly out of scope for v1.

Each type entry should support:

- identifier
- kind: class / interface / enum
- name
- attributes
- methods

Each relationship entry should support:

- source
- target
- kind: inheritance / association / aggregation / composition
- optional multiplicity labels
- optional label text

## File and Module Boundaries

Implementation should keep diagram logic isolated from document templates.

Recommended responsibilities:

- `scripts/diagram_models.py`
  - spec dataclasses or equivalent schema layer
- `scripts/diagram_render_svg.py`
  - Folio-native SVG renderer for diagram artifacts
- `scripts/diagram_export.py`
  - export `SVG -> PNG` and `SVG -> PDF`
- `scripts/build.py`
  - artifact-target integration only, not renderer ownership
- `references/architecture-diagram-spec.md`
  - user-facing architecture spec rules
- `references/uml-class-diagram-spec.md`
  - user-facing UML class spec rules

Existing files that remain important:

- `assets/diagrams/architecture.html`
  - static demo / fallback reference
- `references/diagrams.md`
  - global diagram selection, visual rules, anti-patterns
- `SKILL.md`
  - routing and usage behavior

## Build Integration

### Target model

`scripts/build.py` should gain diagram artifact targets as a separate target family.

They should not be folded into the existing eight document page-contract system.

Suggested behavior:

- artifact build target renders `SVG`
- exports `PNG`
- exports single-page `PDF`
- verifies output existence and export success

### Output placement

Standalone diagram outputs should land in a predictable generated-artifact location, separate from static handwritten diagram templates.

This avoids conflating:

- authored reference templates
- generated outputs

## Routing Changes

`SKILL.md` should evolve from "diagrams are only primitives inside documents" to a dual-path rule:

- standalone diagram request -> diagram artifact pipeline
- embedded diagram request -> generate artifact `SVG`, then embed into host
- slide diagram request -> generate artifact `SVG`, then place into slide

This is a routing expansion, not a document-type expansion.

## Verification

### Required verification

For each artifact kind:

1. Spec can be parsed
2. SVG is generated successfully
3. SVG syntax is valid
4. PNG export succeeds
5. PDF export succeeds
6. PDF is single-page
7. Output stays within Folio token / style constraints

### Style verification

Verification should detect obvious violations such as:

- disallowed cool-gray palette drift
- extra accent colors
- unsupported marker dependence if it breaks PDF stability
- layout overflow or clipped labels

### Fixture strategy

Use a small fixture set for regression:

- 3 architecture fixtures, one per layout family
- 2 UML class fixtures, one simple and one medium-density

The purpose is stability, not exhaustive visual coverage.

## Risks

### 1. Accidentally creating a second design system

Most likely failure mode is borrowing too much from external generator styles. The renderer must stay Folio-native even if some generation concepts come from elsewhere.

### 2. Over-coupling artifacts to document templates

If embedding logic leaks back into rendering logic, slides and standalone output will drift. The renderer must only produce the diagram artifact itself.

### 3. PDF export instability

Arrowheads, label masking, and text clipping can look acceptable in SVG preview but fail in WeasyPrint export. PDF stability must be treated as a first-class acceptance criterion.

### 4. Scope creep into every diagram family

This work should stop at `architecture` and `uml-class` for v1. Expanding to flowchart, sequence, and the rest too early will slow down a clean launch.

### 5. Treating natural language as an input requirement in v1

Natural-language parsing is a second problem. v1 should accept structured specs first so renderer quality and export stability can be proven independently.

## Success Criteria

The design is successful when:

- Folio gains a standalone diagram artifact pipeline without adding a ninth document type
- `architecture` and `uml-class` both generate `SVG + PNG + PDF`
- `SVG` is reused unchanged in documents and slides
- outputs stay visually consistent with current Folio diagrams
- build and routing changes remain local rather than spreading diagram-specific behavior across all templates
