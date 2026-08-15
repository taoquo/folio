# Folio Drawing DSL V4 Contract Audit

Status: implementation complete; release gate in progress  
Audit date: 2026-08-13  
Active phase: V4.0 authoring contracts and developer CLI

## 1. Purpose

V4.0 must make the published authoring contract, runtime compiler boundary, examples, diagnostics, and CLI agree. This audit inventories the current fourteen registered inputs before public validation commands are changed.

## 2. Registry checkpoint

`scripts/drawing/schema_registry.py` now maps every registered compiler kind to one type schema and one canonical compiling fixture. The schema registry and compiler registry both contain fourteen exact keys.

| Kind | Input version | Primary collections | Current schema state |
|---|---|---|---|
| architecture | 3.0 semantic | layers, groups, nodes, edges, legend | Detailed semantic schema; compatible unversioned inputs migrate to 3.0; expert DrawingPlan remains on V2 schema |
| flowchart | 2.0 | nodes, edges | Detailed V2 schema reused through type entrypoint |
| state-machine | 3.0 | states, transitions | Detailed type schema aligned with runtime fields, enums, and budgets |
| swimlane | 3.0 | lanes, steps, flows | Detailed type schema aligned with runtime fields, enums, and budgets |
| tree | 3.0 | nodes, relations | Detailed type schema aligned with runtime fields and budgets |
| layer-stack | 3.0 | layers, flows | Detailed type schema aligned with runtime fields, enums, and budgets |
| timeline | 3.0 | events | Detailed type schema aligned with runtime fields, date shape, and budgets |
| quadrant | 3.0 | axes, items | Detailed type schema aligned with axis structure and normalized domains |
| venn | 3.0 | sets, intersections | Detailed type schema aligned with bounded set topology |
| bar-chart | 3.0 | categories, series | Detailed type schema aligned with series fields and budgets |
| line-chart | 3.0 | categories, series | Detailed type schema aligned with missing values and scale enums |
| donut-chart | 3.0 | segments | Detailed type schema aligned with positive segments and tolerance |
| candlestick | 3.0 | periods | Detailed type schema aligned with OHLC fields and period budgets |
| waterfall | 3.0 | contributions | Detailed type schema aligned with finite numeric fields and tolerance |

## 3. Runtime contract inventory

### Structural

| Kind | Nested fields | Executable invariants |
|---|---|---|
| State Machine | state: id, type, label, description, emphasis; transition: id, source, target, event, guard, action, channel | 1–9 states, max 14 transitions, one initial unless submachine, reachable final unless persistent, max two choices, unique guarded exits, max cycle depth two, one focal state |
| Swimlane | lane: id, label, emphasis; step: id, label, type, lane, emphasis; flow: id, source, target, channel, label | 2–5 lanes, 1–12 steps, owner lane required, max three decisions, max eight handoffs, explicit cross-lane channels, reachable starts, valid focus lane/path |
| Tree | node: id, label, subtitle; relation: id, parent, child | 1–15 nodes, one root, one parent per non-root, acyclic, reachable, depth and breadth budgets, valid focal subtree |
| Layer Stack | layer: id, label, responsibility, emphasis; flow: id, source, target, channel, label | 2–8 ordered layers, unique ids, adjacent direction rules, bounded focal layer, legal dependency channels |

### Positional

| Kind | Nested fields | Executable invariants |
|---|---|---|
| Timeline | event: id, date, label, description, importance | 2–10 events, ISO dates for temporal scale, unique order, valid focus, bounded major events, collision-safe label lanes |
| Quadrant | axes.x/y: label, low, high; item: id, label, x, y, emphasis | 1–12 items, finite normalized coordinates, complete axis meaning, one focal item, deterministic label candidates |
| Venn | set: id, label, exclusive; intersection: id, sets, items | Exactly two or three sets, valid set references, bounded intersections, unique topology, one focus target |

### Data visualization

| Kind | Nested fields | Executable invariants |
|---|---|---|
| Bar | series: id, label, values | 1–8 categories, 1–3 series, finite values, value-count parity, valid focus and explicit order |
| Line | series: id, label, values | 2–12 categories, 1–3 series, finite-or-missing values, missing policy, ordered time scale, value-count parity |
| Donut | segment: id, label, value | 2–6 positive finite segments, positive total, optional 100% tolerance, valid focus |
| Candlestick | period: id, date, open, high, low, close | 1–30 unique ascending ISO periods and `low <= open/close <= high` |
| Waterfall | contribution: id, label, value | 1–8 finite deltas, finite start/end, cumulative arithmetic within tolerance |

## 4. Findings

| Finding | Severity | State | Required action |
|---|---|---|---|
| AUD4-005 | P1 | closed | Architecture semantic input silently ignored unknown top-level and nested fields. Runtime now rejects them, including pixel-coordinate attempts, with regression coverage. |
| AUD4-006 | P1 | closed | All fourteen type entrypoints now contain detailed field, enum, scalar, collection-budget, and unknown-field contracts. Canonical/minimal positive compilation and unknown/missing-field negative parity tests cover every registry key. |
| AUD4-007 | P2 | closed | Architecture semantic input is now public version 3.0. Compatible unversioned payloads migrate idempotently; expert DrawingPlan remains explicitly version 2.0. Metadata records the normalized input major. |
| AUD4-008 | P2 | closed | Public validation and batch commands emit a deterministic envelope containing code, severity, stage, kind, path, message, hint, and related ids. Absolute input paths and exception representations are not exposed. |
| AUD4-009 | P1 | closed | A batch item that became invalid could leave a same-name artifact from an earlier successful run, and export dependency failures could fall through as internal errors. Failure paths now remove the exact collision-safe output target and return the documented dependency exit code without exposing exception details. |

## 5. Mandatory V4.0 order

```text
AUD4-006 detailed type schemas
  -> schema/runtime parity tests
      -> minimal examples and migration policy
          -> registry-derived list/init commands
              -> validate JSON diagnostics
                  -> deterministic batch rendering
                      -> V4.0 release gate
```

No public V4 validation command is complete while AUD4-006 remains open.

## 6. Evidence added

- Fourteen detailed schema files under `references/schemas/types/`.
- A detailed Architecture semantic schema that forbids arbitrary coordinates and unknown fields.
- `DiagramSchemaContract` registry with portable schema, minimal-fixture, and canonical-fixture paths.
- Fourteen maintained minimal fixtures under `references/fixtures/minimal/`.
- Tests proving exact compiler/schema registry coverage, parseable schema JSON, portable metadata, successful minimal/canonical compilation, idempotent migration, and unknown-field rejection for every kind.
- Architecture regression tests proving unknown top-level and nested pixel fields fail before layout.
- Registry-derived `list-diagram-types` and `init-drawing` commands.
- Compiler-backed text/JSON `validate-drawing` and deterministic fail-closed `batch-render-drawings` commands.
- Stable exit codes and JSON diagnostic envelope tests.
- Regression coverage for stale batch artifact removal and dependency exit-code classification.

## 7. Next executable slice

Run the complete V4.0 release gate: install the CI dependency set, execute JSON Schema validation without skips, exercise the 14-type profile/format matrix and deterministic batch replay, run the full test suite, compare the approved catalog baseline, run `build.py --check`, `--sync`, and `--verify`, package the skill, and record the checkpoint. V4.1 may start only after that evidence is clean and no P0/P1 remains open.
