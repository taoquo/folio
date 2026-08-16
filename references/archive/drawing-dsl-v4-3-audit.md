# Folio Drawing DSL V4.3 Registry Expansion Audit

Status: complete  
Audit date: 2026-08-14  
Completed phase: Sequence, UML Class migration, ER, and Sankey decision

## 1. Current-state inventory

The audit began with fourteen registry kinds, a separate coordinate-bearing UML path, and no Sequence or ER compiler. V4.3 closes that state with seventeen registry/schema/catalog kinds. The legacy UML parser and renderer remain callable only as a compatibility facade; production UML build, CLI, catalog, host, and export paths use the shared compiler.

| Surface | Current behavior | Gap |
|---|---|---|
| UML input | Legacy parser accepts types, relationships, and optional author coordinates | No schema version, authoritative detailed schema, collection budgets, recursive unknown-field rejection, or coordinate-free authoring boundary. |
| UML identity | Relationships have no ids; renderer recovers layout edges by `(source, target)` | Parallel relationships collapse and cannot have stable reading-order identity. |
| UML output | Handcrafted SVG omits shared root accessibility metadata, profile attributes, shared primitives, standard scene validation, and registry metadata | Public artifact bypasses the compiler and host traceability contract. |
| Sequence | No contract | Requires ordered participants/messages, lifelines, message grammar, stable ids, bounded vertical budget, and reading order. |
| ER | No contract | Requires entities/fields, primary/foreign keys, cardinality grammar, stable ids, bounded relationship routing, and reading order. |
| Catalog/package | Registry, schema registry, catalog, type counts, compatibility schema, examples, docs, and package are locked to fourteen | Expansion must be registry-derived and release-gated. |
| Sankey | No prototype or decision record | Must prove conservation, deterministic routing, label fit, and a distinct editorial job before registration. |

## 2. Findings

| Finding | Severity | State | Evidence and required action |
|---|---|---|---|
| AUD4-027 | P1 | closed | `artifact-uml-class-demo` now reads the versioned UML fixture, compiles to `CompilationResult`, renders shared `ResolvedScene`, and exports through the standard profile-aware renderer. |
| AUD4-028 | P1 | closed | `uml-class.schema.json` and runtime validation reject coordinates and unknown fields. Public input is coordinate-free `3.0`; legacy loading remains covered separately. |
| AUD4-029 | P1 | closed | UML relationships require stable ids. Duplicate directed endpoint pairs fail closed instead of collapsing in endpoint-pair lookup. |
| AUD4-030 | P2 | closed | Sequence and ER now have compilers, detailed schemas, minimal/canonical fixtures, profiles, accessibility descriptions, catalog, host, docs, CI, and package coverage. |
| AUD4-031 | P2 | closed | Registry/schema/catalog/package gates derive coverage from the registries; obsolete fourteen-type assertions were removed from release-critical tests. |
| AUD4-032 | P2 | closed | ADR 0007 records a V4.3 Sankey no-go with explicit product, conservation, routing, label-fit, and reconsideration criteria. |
| AUD4-033 | P1 | closed | Initial notation semantic-mark construction allowed source ids to overwrite prefixed ids. Merge order is fixed and tests require stable `participant:`, `message:`, `type:`, `entity:`, and `relationship:` identities. |
| AUD4-034 | P1 | closed | Initial notation scenes lacked item-overlap, route attachment, orthogonality, unrelated-item crossing, density, and text-fit gates. The compiler now validates each condition and fails before export. |
| AUD4-035 | P2 | closed | Initial box routes retained duplicate points and notation metrics reported zero edges. Routes are normalized and notation metrics report exact relationship, label, and bend counts. |

No P0 was found. No P1 or P2 remains open.

## 3. Intended compiler contracts

### Sequence

- 2–6 participants; kinds `actor`, `system`, or `store`.
- 1–12 ordered messages; kinds `sync`, `async`, or `return`.
- Stable participant/message ids, known endpoints, no self-message until loopback routing is explicitly supported.
- One horizontal participant axis and one downward time axis; author input cannot set coordinates or paths.
- Message order is semantic reading order; lifelines and arrowheads use shared primitives.

### UML Class

- 1–8 types; kinds `class`, `interface`, or `enum`.
- Bounded attributes/methods and 0–12 relationships.
- Stable relationship ids; kinds `inheritance`, `association`, `aggregation`, or `composition`.
- Coordinate-free deterministic class grid/ELK layout; no duplicate directed endpoint pair.
- The legacy loader/render facade remains callable, but standard build/catalog/CLI/host paths use the registry compiler.

### ER

- 2–8 entities with 1–8 fields each; at least one primary key per entity.
- Field types are bounded text, with explicit primary key, foreign key, and nullable flags.
- 1–12 relationships with stable ids, known distinct endpoints, short labels, and cardinalities `one`, `zero-or-one`, `many`, or `one-or-many`.
- Deterministic entity grid, orthogonal relations, key markers, accessible field descriptions, and no physical database coordinates.

## 4. Sankey decision bar

Registration requires all of the following in a bounded 960×540 prototype:

1. exact source/target flow conservation with explicit diagnostics;
2. deterministic node/link order and stable ids under input replay;
3. no uncontrolled link crossings for the maximum supported graph;
4. readable labels and materially clearer communication than existing Waterfall, Layer Stack, or Architecture types.

If any bar fails, V4.3 records a no-go ADR and leaves Sankey outside the public registry.

## 5. Exit gate

V4.3 completes only when Sequence, UML Class, and ER are production registry compilers with detailed schemas, minimal/canonical/CJK/dense/invalid fixtures, deterministic three-profile/three-format coverage, accessibility, catalog, CLI, host, package, docs, and compatibility tests; Sankey has a recorded go/no-go; all audit findings are closed; and the final standard release gate passes with classified visual evidence.

## 6. Completion evidence

| Gate | Result |
|---|---|
| Registry/schema/catalog | 17 compiler keys, 17 schema contracts, 17 generator-backed catalog entries; exact parity. |
| Tests | 198 passed; 3 dependency-conditional skips; notation semantics, negative contracts, density, route crossing, text fit, profiles, formats, host, CLI, package, and legacy compatibility covered. |
| Profile/format matrix | 153 canonical artifacts: 17 kinds × 3 profiles × SVG/PNG/PDF. |
| Determinism | Two independent 17-fixture minimal batches produced identical reports and SVG SHA-256 digests. |
| Visual | 17 approved page-preview diagrams pass exact baseline comparison; Sequence, UML Class, and ER were manually reviewed before approval. |
| Build | `doctor`, `build.py --check`, `--sync`, and full `--verify` pass, including five diagram artifacts and four document/slide host products. |
| Compatibility | Legacy UML loader/layout/renderer, existing fourteen diagram types, V2/V3 CLI, document templates, slide templates, and host verification remain green. |
| Sankey | No-go accepted in `decisions/0007-sankey-is-not-a-v4-3-grammar.md`. |
| Package | Final package is below 5 MB and includes all V4.3 runtime, schema, fixture, test, audit, ADR, and documentation sources. |
