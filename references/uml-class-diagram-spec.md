# UML Class Diagram Spec

Production UML Class input uses `schema_version: "3.0"`, `kind: "uml-class"`, and optional `layout: "class-grid"`. Start from `references/fixtures/minimal/uml-class.json` or `references/fixtures/v4/uml-class.json`; the authoritative contract is `references/schemas/types/uml-class.schema.json`.

Authors provide type members and relationships, never `x`, `y`, box dimensions, connector paths, colors, or SVG. The compiler owns a bounded 960×640 grid, shared scene validation, accessibility metadata, output profiles, and SVG/PNG/PDF serialization.

Supported type kinds:

- `class`
- `interface`
- `enum`

Supported relationship kinds:

- `inheritance`
- `association`
- `aggregation`
- `composition`

Each type and relationship requires a stable id. The grammar accepts 1–8 types, up to 6 attributes and 5 methods per type, and 0–12 relationships. A relationship references two distinct known types. Duplicate directed endpoint pairs are rejected because V4.3 does not route parallel relationships.

The older unversioned `references/fixtures/uml-class-demo.json` and `diagram_models.py` loader remain callable for compatibility tests only. Production CLI, catalog, host, and build artifact paths use the versioned registry compiler.
