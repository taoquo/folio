# Folio Drawing DSL V4.0 Completion Audit

Status: complete  
Completion date: 2026-08-13  
Scope: authoritative authoring contracts and developer CLI

## 1. Outcome

V4.0 closes the gap between the fourteen registered compilers, published schemas, maintained examples, migration metadata, validation diagnostics, and public command surface. No P0 or P1 finding remains open.

## 2. Delivered contract

- Fourteen authoritative type schemas under `references/schemas/types/`.
- Fourteen minimal fixtures under `references/fixtures/minimal/` and fourteen canonical fixture mappings in the schema registry.
- Exact compiler/schema registry parity with portable schema and fixture paths.
- Architecture semantic input version 3.0 with idempotent migration from compatible unversioned input; expert Architecture DrawingPlan remains version 2.0.
- Registry-derived `list-diagram-types` and `init-drawing`.
- Compiler-backed `validate-drawing` with deterministic text and JSON contracts.
- Atomic `render-drawing` and collision-safe, stable-order, fail-closed `batch-render-drawings`.
- Stable exit codes: success 0, invalid input 1, dependency/file failure 2, internal failure 3.
- JSON diagnostics containing code, severity, stage, kind, path, message, hint, and related ids.
- Intent-first authoring guide in `drawing-dsl-authoring.md`.

## 3. Closed findings

| Finding | Severity | Resolution |
|---|---|---|
| AUD4-005 | P1 | Architecture semantic input rejects unknown top-level and nested fields, including pixel overrides. |
| AUD4-006 | P1 | Replaced generic V3 wrapper contracts with detailed per-type schemas and positive/negative parity coverage. |
| AUD4-007 | P2 | Normalized Architecture semantic authoring to version 3.0 with idempotent compatibility migration. |
| AUD4-008 | P2 | Added the stable V4 JSON diagnostic envelope and deterministic ordering. |
| AUD4-009 | P1 | Invalid batch items remove exact stale targets; dependency failures return code 2 and cannot leave partial output. |

## 4. Release-gate evidence

| Gate | Evidence |
|---|---|
| Schema validation | `jsonschema` 4.23.0 executed all seven schema-registry tests without skips. |
| Tests | 159 discovered tests passed with the CI dependency path active. |
| Positive examples | Minimal and canonical fixtures compile for all fourteen registry keys. |
| Negative examples | Every public contract rejects unknown fields; nested unknown/missing fields and runtime semantic invariants have regression coverage. |
| Public workflows | Text and JSON contracts cover list, init, validate, render, and batch. |
| Determinism | Two independent 14-item batch runs produced identical reports and SVG SHA-256 digests. |
| Profile/format matrix | The full suite generated and inspected 126 artifacts: fourteen kinds × three profiles × SVG/PNG/PDF. |
| Accessibility | Every compiled scene passed title, description, language, reading-order, primitive, and canvas checks through the compiler boundary. |
| Visual baseline | Fourteen approved page-preview PNGs passed exact RGBA comparison with maximum changed-channel ratio 0.0. |
| Metadata approval | Architecture moved from `architecture@2` to `architecture@3`; input digest changed, while SVG/PDF/PNG digests and geometry remained exact. The baseline records the explicit metadata-only approval reason. |
| Templates | `build.py --check` and `build.py --sync` passed across thirty templates. |
| Full artifacts | `build.py --verify` passed all document, diagram, artifact, and slide targets. |
| Package | `dist/folio.zip` rebuilt successfully at 2,014,950 bytes with 263 verified files and required V4 schemas, fixtures, code, tests, and guide included. |
| Source hygiene | `git diff --check` passed. |

## 5. Compatibility

V3 inspection, render, review, catalog, migration, schema-validation, and bundle entrypoints remain covered. Flowchart remains input version 2.0. Architecture expert DrawingPlan remains input version 2.0. Existing SVG, PNG, PDF, document, and slide build targets remain green.

## 6. Residual risk and next entry

The hosted GitHub workflow still requires a repository push to execute remotely; its YAML parses locally and every constituent command has passed locally. This does not leave an implementation defect open.

V4.1 may begin with a host-contract audit. It must inventory current HTML `<figure>` and PPTX image-slot behavior before introducing A4, Letter, 16:9, and responsive embedding contracts. Any discovered P0/P1 must be fixed before host integration expands.
