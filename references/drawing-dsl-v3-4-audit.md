# Folio Drawing DSL V3.4 Release Audit

Status: complete  
Audit date: 2026-08-13  
Scope: public drawing CLI, compiler registry, catalog, exporters, dependency diagnosis, packaging, visual baselines, compatibility paths, tests, and release verification

## 1. Outcome

V3.4 closes the production-readiness gap after V3 Gate R. The fourteen-type registry and catalog remain aligned, all public compile and export commands continue to cross `CompilationResult`, deterministic catalog replay passes, an approved visual baseline is enforced, and the repository now has fast and full CI gates.

No P0 or P1 finding remains open.

## 2. Findings and closure

| Finding | Severity | State | Closure evidence |
|---|---|---|---|
| AUD4-001 | P1 | closed | `doctor` now accepts the functional project WeasyPrint fallback and checks required `pdftoppm` instead of optional `pdffonts`; three regression tests cover failure, fallback, and rasterizer selection. |
| AUD4-002 | P1 | closed | `package-skill.sh` no longer uses macOS-only `stat -f%z`; POSIX `wc -c` size validation passes and the package test exercises the current source set. |
| AUD4-003 | P2 | closed | V3 catalog validation now derives its type set from `DiagramCompilerRegistry`; duplicated hard-coded catalog counts and CLI wording were removed. |
| AUD4-004 | P2 | closed | The catalog previously recorded artifact digests but not semantic reading-order ids or an enforceable approved baseline; the V3.4 baseline and comparison command now gate both. |

## 3. Pipeline audit

Public commands inspected:

- `draw-semantic`
- `draw-plan`
- `draw-scene`
- `draw-layout`
- `check-drawing`
- `draw-metrics`
- `migrate-drawing`
- `validate-drawing-schema`
- `bundle-drawing`
- `render-drawing`
- `review-drawing`
- `diagram-catalog`

Architecture and Flowchart compatibility functions remain available for existing callers. Their public SVG artifact adapters compile through `DEFAULT_COMPILER_REGISTRY`. Type-owned low-level compilers remain internal implementation and unit-test surfaces; no inspected public exporter constructs a scene from unvalidated user input.

## 4. Determinism and visual governance

Two independent catalog runs produced identical normalized coverage, dimensions, content bounds, diagnostics, metrics, input digests, SVG digests, PDF digests, PNG digests, and contact-sheet digests.

The approved baseline is `references/fixtures/drawing/catalog-baseline-v3.json`. It records:

- approval state and reason;
- output profile and registry key;
- semantic reading-order ids;
- source and output dimensions;
- content bounds;
- input, SVG, PDF, and PNG digests;
- exact no-resize pixel-diff method;
- a 1% changed-channel ceiling and 2 px bounds tolerance.

The final comparison reported fourteen passing diagrams, no issues, a maximum changed-channel ratio of `0.0`, and no digest mismatches.

## 5. CI and package

`.github/workflows/drawing-dsl.yml` defines:

1. a fast gate for dependency diagnosis, focused tests, template/token checks, registry/catalog validation, and package-content validation;
2. a release gate for all tests, approved visual-baseline comparison, full build verification, release packaging, and evidence upload.

CI dependencies are pinned in `requirements-ci.txt`. The package contains the approved baseline plus all fourteen baseline PNGs so comparison remains available from the distributed skill. Final package size is `1,984,306` bytes, below the 5 MB limit.

## 6. Verification evidence

| Gate | Result |
|---|---|
| Dependency doctor | pass; 8 / 8 checks |
| Automated tests | 145 passed |
| Template rules | 30 templates, no violations |
| Token synchronization | 30 templates in sync |
| Catalog coverage | 14 / 14 Drawing DSL V3 |
| Catalog diagnostics | 0 errors |
| Visual baseline | 14 passed, 0 issues |
| Full build verification | all document, diagram, artifact, and slide targets passed |
| Package verification | pass, 14 baseline PNGs included, below 5 MB |
| Diff hygiene | `git diff --check` passed |

## 7. Compatibility evidence

- Architecture raw text, semantic input, and handwritten V2 DrawingPlan paths remain valid.
- Flowchart compile, check, scene, render, and review paths remain valid.
- UML Class remains on its separate notation-specific generator and passes artifact build verification.
- V1-to-V2 migration, V2 schema validation, DrawingBundle generation, and review-bundle metadata have explicit CLI regression tests.
- Existing document, diagram, artifact, and slide build targets remain green.

## 8. Residual risks

- The hosted workflow will first execute after the repository changes are pushed; the YAML, dependency checks, package flow, full tests, catalog comparison, and build commands were validated locally.
- Pixel comparison deliberately allows small cross-platform raster differences up to 1%; semantic ids, SVG digest, dimensions, and bounded content geometry remain exact gates.

Neither residual item is a P0 or P1 defect. The next phase may begin.

## 9. Next entry condition

V4.0 starts with per-type authoring-contract inventory. The first slice must map each registered compiler's runtime validation to an authoritative type schema before changing public CLI behavior.
