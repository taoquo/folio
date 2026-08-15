# Architecture Drawing Grammar

This document describes the executable grammar used by generator-backed architecture diagrams. The code in `scripts/drawing/grammar/architecture.py` is the source of truth; this file explains the intent.

## Information budget

- Target density: 4/10.
- Maximum nodes: 9.
- Maximum focal semantic objects: 2.
- Maximum visible edge labels before warning: 6.
- Maximum regions before warning: 4.
- Maximum connector arrows before reduction or split warning: 12.

Reduction actions are `merge`, `drop`, `background`, and `split`. Decorative nodes are not valid evidence for inclusion.

## Composition

- `layered`: ordered system regions such as surface, runtime, and data.
- `pipeline`: an ordered ingest-transform-serve path.
- `hub`: one orchestration center with supporting systems.

The primary reading path is the `spine`. Supporting nodes may be sidecars of a spine owner. Neither construct exposes pixel coordinates.

## Canonical generator geometry

| Token | Value |
|---|---:|
| Grid | 4 |
| Node width | 176 |
| Node height | 72 |
| Node gap | 48 |
| Layer gap | 96 |
| Edge-to-node gap | 24 |
| Edge-to-edge gap | 18 |

These values preserve the existing generator baseline. They are separate from the smaller size tiers used by hand-authored inline SVG templates.

## Connectors

- `primary-flow`: solid and stronger.
- `secondary-flow`: solid and neutral.
- `async-flow`: dashed and muted.
- A focal path is an emphasis override, not a fourth relationship type.

Top-down compositions prefer south-to-north ports across layers and east-to-west ports within a layer. Left-right compositions prefer east-to-west ports. Connector postprocessing removes duplicate points, zero-length segments, and collinear intermediate points while keeping endpoints fixed on node edges.

Each connector exits its node perpendicular to the selected side. Attach points fan out by at least 12 units. Routes are orthogonal, elbows resolve to an 8-unit radius, visible labels are uppercase and no longer than 14 characters, and label masks create a clear 6–10 unit gap. Unavoidable crossings resolve with bridge hops; collinear connector overlap is a geometry error.

Arrowheads are resolved manual open chevrons. SVG markers are not used.

## Typography

Text uses semantic roles rather than renderer constants: diagram title, region label, node eyebrow, node title, node metadata, edge label, annotation, and legend.

Node titles keep a 12-unit minimum and wrap to at most two lines. Metadata keeps a 9-unit minimum and is dropped before text is shrunk. Deterministic measurement estimates ASCII serif at `0.55 x size`, ASCII mono at `0.62 x size`, and CJK at `1.0 x size`.

## Theme

Drawing plans contain emphasis roles, never palette values. The Folio theme maps focal objects to cinnabar-coral and brand tint, normal objects to warm neutrals, and background objects to low-contrast stone. Renderer code receives only resolved values.

## Controlled visual review

The review artifact is `assets/demos/drawing-dsl-before-after.png`. It compares the frozen `HEAD` baseline with the Drawing DSL result for Agent Runtime, Workflow Engine, and Data Platform.

| Dimension | Baseline | Drawing DSL | Goal |
|---|---:|---:|---|
| Semantic fidelity | Preserved | Preserved through SemanticDiagram snapshots | Preserve |
| Node overlap | 0 | 0 | Zero |
| Connector overlap | Not enforced | 0, validator-enforced | Improve |
| Crossing count | Visually reviewed | 0 / 0 / 0 | No worse |
| Spine bends | Not machine-readable | 2 / 2 / 4 | Expose and control |
| Text overflow | Not machine-readable | 0 / 0 / 0 | Zero |
| Focal count | 1 / 1 / 1 | 1 / 1 / 1 | 1–2 |
| Folio identity | Present | Preserved | Preserve |

The metric triplets are ordered Agent Runtime / Workflow Engine / Data Platform. The Data Platform spine keeps four bends because two spine nodes intentionally share the data layer; this is surfaced as a `TASTE DG201` diagnostic rather than hidden by a score.
