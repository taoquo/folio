# Architecture Semantic Planning Design

**Goal:** Add a semantic planning layer between raw technical text and Folio's diagram renderer so architecture diagrams can reflect mechanism, ownership, and runtime flow instead of only surface topology.

## Decision

Folio should not push more system understanding into the SVG renderer.

Instead, architecture generation will be split into three stages:

1. **Text Understanding**
   - read detailed source text
   - extract structure, runtime behavior, ownership, and emphasis
2. **Semantic Spec Planning**
   - convert extracted meaning into a richer architecture spec
   - choose layout, groups, focus path, and edge semantics
3. **Rendering**
   - draw the diagram faithfully from the planned spec

The renderer remains deterministic and visual. The new intelligence belongs in the planning layer.

## Why This Layer Is Needed

The current artifact pipeline can render clean Folio-style diagrams, but the architecture spec is too shallow to carry strong system semantics.

Today it can express:

- layers
- node kind
- edge kind
- label
- focus node

That is enough to draw a structurally valid diagram, but not enough to distinguish:

- ownership vs orchestration
- query vs writeback
- control flow vs data flow
- main path vs support path
- runtime loop vs initialization path

Without those distinctions, detailed technical text is flattened into generic boxes and lines.

## Problem Statement

For complex systems, especially game engines, agent runtimes, workflow systems, and data platforms, users do not merely want a component inventory.

They want the diagram to answer:

- what is the system's center of gravity
- what triggers what
- what owns state
- what reads state
- what writes state
- what belongs to setup time vs frame time vs async background work

Those answers should be inferred before rendering begins.

## New Architecture Generation Model

### Stage 1: Text Understanding

Input can be:

- architecture notes
- white-paper prose
- design doc sections
- bullets from a meeting
- source comments or README excerpts

This stage extracts normalized meaning, not visual coordinates.

Expected output categories:

1. **System structure**
   - layers
   - subsystems
   - components
   - external actors

2. **Runtime semantics**
   - scheduling
   - ownership
   - read paths
   - write paths
   - event paths
   - background / async behavior

3. **Narrative emphasis**
   - focal node
   - focal path
   - key claim the diagram should support

4. **Visual planning hints**
   - likely layout family
   - likely groupings
   - likely edge strengths

This stage should not emit SVG terms such as `x`, `y`, `width`, `path`, or direct drawing commands.

### Stage 2: Semantic Spec Planning

This stage converts extracted meaning into a diagram-ready semantic spec.

It chooses:

- layout family
- layer grouping
- node roles
- edge semantics
- focus path
- container boundaries
- legend items
- route hints when needed

This stage is the bridge between language and graphics.

### Stage 3: Rendering

The renderer takes the semantic spec and produces:

- `SVG`
- derived `PNG`
- derived `PDF`

Renderer responsibilities stay narrow:

- layout execution
- line routing
- node drawing
- relationship markers
- label placement
- Folio styling

Renderer must not infer business meaning.

## Proposed Semantic Architecture Spec

The current `architecture` spec should evolve from a thin visual schema into a semantic schema with room for runtime meaning.

### Top-Level Fields

- `kind`
- `title`
- `subtitle`
- `caption`
- `layout`
- `width`
- `height`
- `focus_node`
- `focus_path`
- `focus_reason`
- `layers`
- `groups`
- `nodes`
- `edges`
- `legend`

### Layer Fields

Each layer should support:

- `id`
- `label`
- `purpose`
- `order`

This allows the text-understanding step to distinguish a display band from an execution band instead of treating layers as decorative row labels only.

### Group Fields

Groups represent subsystems or containers within layers.

Each group should support:

- `id`
- `label`
- `kind`
- `layer`
- `members`
- `side_label`
- `summary`

Example group kinds:

- `subsystem`
- `runtime-loop`
- `storage-tier`
- `ingress`
- `background-worker`

### Node Fields

The current node schema should expand to include:

- `id`
- `label`
- `kind`
- `role`
- `layer`
- `group`
- `sublabel`
- `description`
- `importance`
- `state_owner`
- `lifecycle_phase`

#### `kind`

Visual class. Conservative set for Folio:

- `external`
- `service`
- `store`
- `cloud`

#### `role`

Semantic class. This is the important addition.

Suggested initial vocabulary:

- `entry`
- `scheduler`
- `orchestrator`
- `executor`
- `world`
- `system`
- `query-engine`
- `cache`
- `resource-loader`
- `storage`
- `event-bus`
- `renderer`
- `tool-runtime`

`kind` drives appearance. `role` drives planning, labeling, and emphasis.

#### `importance`

Allows planning to choose focal treatment without hardcoding color too early.

Suggested values:

- `primary`
- `secondary`
- `background`

#### `state_owner`

Boolean or enum expressing whether this node is a durable owner of runtime state.

This matters because systems such as ECS have a sharp distinction between:

- state owners
- state readers/writers

#### `lifecycle_phase`

Useful for systems where initialization and hot-path runtime should be visually separated.

Suggested values:

- `bootstrap`
- `runtime`
- `background`
- `shutdown`

### Edge Fields

The current edge model is too coarse. It should expand to:

- `source`
- `target`
- `flow`
- `interaction`
- `label`
- `priority`
- `dashed`
- `source_port`
- `target_port`
- `route_hint`
- `phase`

#### `flow`

High-level semantic category.

Suggested values:

- `control`
- `read`
- `write`
- `query`
- `event`
- `stream`
- `sync`
- `async`

This is much stronger than the current `primary / secondary / async`.

#### `interaction`

Short verb that explains the relationship from the source perspective.

Suggested values:

- `owns`
- `schedules`
- `queries`
- `reads`
- `writes`
- `publishes`
- `subscribes`
- `loads`
- `mutates`
- `emits`

`flow` and `interaction` are related but not identical:

- `flow` helps visual semantics
- `interaction` helps diagram wording and caption truthfulness

#### `priority`

Controls emphasis planning.

Suggested values:

- `primary`
- `secondary`
- `background`

#### `phase`

Allows edges to be grouped by runtime stage:

- `bootstrap`
- `runtime`
- `background`

This is useful when the same pair of nodes interact differently during load time and frame time.

#### `route_hint`

Planning-only hint, not raw geometry.

Suggested shape:

- `straight`
- `orthogonal`
- `avoid_center`
- `drop_to_lower_layer`
- `rise_to_upper_layer`

The planner may later compile this into renderer-friendly fields such as explicit ports or corridor hints.

### Legend Fields

Legend should stop being a passive string list and become semantic.

Each legend item should support:

- `flow`
- `label`
- `reason`

This lets the planner include only distinctions that matter for the current diagram.

## ECS Worked Example

### Source Text

A typical user input might say:

> The game engine uses an ECS runtime. Input events and scene loading feed a fixed-tick scheduler. The scheduler advances the ECS world each frame. Systems query entities by component masks, mutate component stores, and stream resources through a cache. The world owns entity lifetimes and component registration, while systems do not own persistent state.

### Text Understanding Output

From that text, the understanding layer should infer:

- **center of gravity**: `World`
- **runtime driver**: `Frame Scheduler`
- **execution band**: `System Pipeline`
- **state owners**: `World`, `Component Stores`, `Resource Cache`
- **non-owners**: `MovementSystem`-style executors
- **main path**: input/load -> scheduler -> world -> systems
- **secondary path**: systems -> stores/resources

### Planned Semantic Spec

The planner should then produce something like:

- `focus_node = "world"`
- `focus_path = ["scheduler", "world", "systems"]`
- `layers = ["surface", "runtime", "data"]`
- `role(world) = "world"`
- `role(scheduler) = "scheduler"`
- `role(systems) = "executor"`
- `state_owner(world) = true`
- `flow(world -> systems) = "query"`
- `interaction(world -> systems) = "exposes"`
- `flow(systems -> stores) = "write"`
- `interaction(systems -> stores) = "mutates"`

The renderer should not need to infer any of this.

## Planned Text-To-Spec Extraction Responsibilities

The text-understanding layer should answer these questions explicitly:

### 1. What are the layers?

Examples:

- Surface / Runtime / Data
- Client / Gateway / Services / Storage
- Interface / Core / Foundation

### 2. What are the components?

It should find named runtime units and normalize aliases:

- `ECS World` and `world state` may refer to the same node
- `system executor` and `system pipeline` may refer to one execution band

### 3. What are the ownership relationships?

This is critical for engine and agent diagrams.

Examples:

- world owns entities
- stores own dense arrays
- systems do not own state

### 4. What are the runtime interactions?

Not just "connected to", but:

- scheduler advances world
- systems query world
- systems write component stores
- loader populates resource cache

### 5. What is the main story?

This determines focus.

Examples:

- request path
- frame loop
- retrieval loop
- writeback loop

Without this, the diagram has no rhetorical center.

## Planner Output Contracts

The planner should guarantee:

1. Every node has one `role`
2. Every edge has one `flow`
3. Every diagram has either a `focus_node` or `focus_path`
4. Every layer has a semantic purpose, not only a label
5. Every emphasized edge has a reason

If these are missing, the planner should fail or degrade explicitly rather than silently produce a generic diagram.

## Boundaries

### What the text-understanding layer should do

- infer semantics
- normalize terminology
- classify relationships
- choose narrative emphasis
- choose spec fields

### What the renderer should not do

- decide which node is the true core
- guess whether an edge is query vs write
- infer ownership from names
- guess lifecycle phase
- guess legend meaning

### What stays out of scope for now

- full natural-language parser implementation
- automatic package grouping for UML
- codebase-aware diagram extraction from source AST
- cross-document memory of system naming conventions

## Risks

### 1. Too much meaning hidden in labels

If semantic meaning stays trapped inside freeform labels, the planner cannot make reliable visual choices.

### 2. Renderer tempted to keep guessing

Any time the renderer "helpfully infers" flow or ownership, the architecture boundary erodes.

### 3. Overly broad role vocabulary

If role taxonomy grows without discipline, planning becomes inconsistent. Start with a small controlled vocabulary.

### 4. Premature natural-language optimism

The right order is:

1. define semantic spec
2. define extraction questions
3. then implement text-to-spec

Skipping step 1 produces brittle prompt magic instead of a reliable system.

## Success Criteria

This design is successful when:

- architecture diagrams can express mechanism, not only topology
- `ECS`-style systems can distinguish state owners from runtime executors
- `focus_path` exists as a first-class planning concept
- semantic roles and flow types are defined outside the renderer
- a future text-understanding module has a stable target schema to populate
