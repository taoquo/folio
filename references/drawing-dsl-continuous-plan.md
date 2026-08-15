# Folio Drawing DSL Continuous Implementation Plan

Status: complete  
Program start: 2026-08-13  
Program completion: 2026-08-14  
Predecessor: `drawing-dsl-v3-completion-goal.md`

## 1. Objective

Evolve the completed fourteen-type Drawing DSL V3 into a production-ready, easy-to-author, document-native V4 platform without weakening deterministic layout, fail-closed validation, accessibility, or Folio's constrained visual language.

This is a continuous execution program rather than a backlog. Work proceeds through one active phase at a time. Every phase begins with a logic audit, closes confirmed defects with regression tests, ships implementation and documentation together, and records enough evidence for the next execution session to resume without repeating completed work.

The program is complete only when V3.4 and V4.0 through V4.3 pass their release gates, all required compilers and compatibility paths are production-backed, and no P0 or P1 finding remains open.

## 2. Starting checkpoint

The V3 checkpoint on 2026-08-13 is the program baseline:

| Capability | Baseline |
|---|---|
| Generator-backed official catalog | 14 / 14 types |
| Shared compiler boundary | `DiagramCompilerRegistry` plus `CompilationResult` |
| Output matrix | 14 types x 3 profiles x 3 formats = 126 combinations |
| Output profiles | `artifact`, `embed`, `page-preview` |
| Full automated tests | 138 passing |
| Build gates | `--check`, `--sync`, and `--verify` passing |
| Catalog diagnostics | 14 approved, 0 errors |
| Package | `dist/folio.zip`, below 5 MB |
| Open V3 audit findings | 0 P0, 0 P1 |

The working tree contains the completed V2/V3 implementation and generated artifacts. Preserve those changes. Do not reset, discard, or silently replace them while executing this program.

## 3. Execution contract

### 3.1 Continuous loop

Every work package uses this loop:

```text
resume checkpoint
  -> inspect current implementation and worktree
  -> audit the active scope
  -> fix blocking P0/P1 findings first
  -> implement the smallest complete vertical slice
  -> add positive, negative, compatibility, and deterministic tests
  -> regenerate only affected review artifacts
  -> run the phase gate
  -> record evidence, residual risks, and the next entry condition
```

Do not start a successor phase while its predecessor has open P0/P1 findings or a failed release gate. P2 findings may be deferred only with a documented reason, bounded impact, and a named target phase.

### 3.2 Work-item states

Use exactly one state per work item: `pending`, `in progress`, `blocked`, `verification`, or `complete`. At most one release phase may be `in progress`.

A work item becomes `complete` only when:

1. its implementation is present;
2. positive and negative regression tests pass;
3. generated manifests or visual baselines are current;
4. affected public documentation matches behavior;
5. the active phase gate passes.

### 3.3 Defect severity

| Severity | Meaning | Execution rule |
|---|---|---|
| P0 | Corruption, unsafe output, invalid artifact emitted as valid, or broad release failure | Stop feature work and repair immediately |
| P1 | Contract bypass, semantic loss, non-determinism, clipping, inaccessible output, or compatibility break | Repair before continuing the active phase |
| P2 | Bounded quality, diagnostics, performance, or maintainability defect | Fix in phase when practical; otherwise record owner phase |
| P3 | Taste improvement or low-impact cleanup | Keep outside the release gate unless explicitly promoted |

## 4. Release train

| Phase | Outcome | Estimate | Dependency | State |
|---|---|---:|---|---|
| V3.4 | Production stabilization and releasable baseline | 3–5 engineering days | V3 complete | complete |
| V4.0 | Authoring contracts and developer CLI | 7–10 engineering days | V3.4 | complete |
| V4.1 | Native document and slide integration | 7–10 engineering days | V4.0 | complete |
| V4.2 | Data Viz authoring and annotation expansion | 8–12 engineering days | V4.1 | complete |
| V4.3 | Sequence, UML registry migration, ER, and conditional Sankey | 15–24 engineering days | V4.2 | complete |

Estimates are planning ranges, not release gates. Correctness and evidence determine completion.

## 5. V3.4 — Production stabilization

### 5.1 Logic and release audit

- Re-run the closed V3 audit against current public CLI, registry, catalog, renderer, exporters, package contents, and generated artifacts.
- Search for bypass paths that construct layouts, scenes, or artifacts without `CompilationResult`.
- Check registry, schema, fixture, catalog, README, and `SKILL.md` type counts for drift.
- Check deterministic digests from two clean catalog runs.
- Classify every finding and close P0/P1 before other V3.4 work.

### 5.2 Continuous integration

- Add a repository CI workflow using the supported Python runtime and system dependencies.
- Split fast checks from render-heavy verification while preserving one full release job.
- Fast job: unit tests, `build.py --check`, `build.py --sync`, schema validation, and package-content checks.
- Release job: full tests, catalog regeneration in a temporary output root, deterministic replay, `build.py --verify`, and `package-skill.sh`.
- Cache dependencies only; never cache generated verification output as evidence.

### 5.3 Visual baseline governance

- Define a committed baseline manifest containing dimensions, content bounds, profile, digest, diff method, and approval state.
- Add a comparison command that fails on dimension mismatch, new clipping, missing artifacts, unclassified large diffs, or changed semantic ids.
- Require an explicit reason when approving a changed visual baseline.
- Keep generated contact sheets for human review, but make manifest checks the automated source of truth.

### 5.4 Naming and compatibility cleanup

- Inventory V1/V2/V3 names, legacy facades, and public commands.
- Keep supported V3 entrypoints working through thin adapters.
- Deprecate ambiguous commands in diagnostics and documentation before removal; do not remove them in V3.4.
- Eliminate duplicated type lists by deriving public listings from the registry where possible.
- Add compatibility tests for Architecture, Flowchart, UML Class, build targets, and all public drawing CLI commands.

### 5.5 Release artifact

- Produce release notes in the repository's bilingual release format.
- Regenerate the catalog, demos, and `dist/folio.zip` from the release candidate.
- Verify the package contains the compiler, schemas, fixtures, tests, docs, and no excluded font payload.
- Record versions, artifact digests, test count, catalog coverage, and known P2/P3 items.

### 5.6 V3.4 exit gate

- No open P0/P1 finding.
- CI passes from a clean checkout-equivalent environment.
- Two catalog runs have identical semantic and artifact digests.
- Visual changes are either absent or explicitly classified and approved.
- All existing V3 public commands and compatibility adapters pass.
- Full tests, `--check`, `--sync`, `--verify`, and package creation pass.
- V3.4 checkpoint and release notes are complete.

## 6. V4.0 — Authoring contracts and developer CLI

### 6.1 Authoritative per-type schemas

- Replace the broad published V3 union as the authoring source with one detailed schema per registered type.
- Keep shared definitions only for truly shared fields such as version, kind, title, language, profile-neutral metadata, ids, and diagnostics.
- Encode required fields, enums, references, uniqueness constraints that JSON Schema can express, numerical bounds, and `additionalProperties` policy.
- Keep semantic invariants that JSON Schema cannot express in type validators with stable diagnostic codes.
- Add schema/runtime parity tests so a published-valid fixture cannot fail merely because the runtime contract differs.

### 6.2 Discoverable CLI

Implement a small, composable command surface:

```text
folio list-diagram-types [--format text|json]
folio init-drawing <kind> [--language <code>] [--output <path>]
folio validate-drawing <path> [--format text|json]
folio render-drawing <path> --profile <profile> --format <format>
folio batch-render-drawings <input> --output-dir <dir> [--fail-fast]
```

- `list-diagram-types` is registry-derived and reports schema versions and supported profiles/formats.
- `init-drawing` emits a minimal valid, commented-free JSON fixture with no invented business content.
- `validate-drawing` validates without exporting and uses the same compiler boundary as render.
- Batch rendering has stable ordering, per-input status, aggregate exit status, collision-safe output names, and no partial output for an invalid item.
- Keep legacy command names as tested aliases during V4.0.

### 6.3 Machine-readable diagnostics

- Define one JSON diagnostic envelope containing code, severity, stage, kind, path, message, hint, and related ids.
- Make ordering deterministic by stage, code, path, and related id.
- Prevent Python exceptions, absolute temporary paths, or unstable object representations from leaking into the contract.
- Document exit codes for valid, invalid-input, dependency, and internal-error cases.

### 6.4 Migration and examples

- Add schema-major migration hooks with idempotency tests.
- Supply one minimal and one canonical fixture per type.
- Validate every example shown in documentation during tests.
- Add a concise authoring guide that starts from intent and semantic data, not coordinates.

### 6.5 V4.0 exit gate

- Fourteen detailed schemas pass schema/runtime parity tests.
- All five CLI workflows pass text and JSON contract tests.
- Batch rendering is deterministic and fail-closed.
- Every registered type has validated minimal and canonical examples.
- V3 commands remain green through compatibility adapters.
- Standard full release gate passes.

## 7. V4.1 — Native document and slide integration

### 7.1 Host profiles

- Add explicit host contracts for A4 portrait, Letter portrait, 16:9 slide, and responsive HTML embed.
- Derive fit, safe area, target pixel density, and caption spacing from host contracts rather than diagram-type branches.
- Preserve the three existing output profiles; host contracts specialize embedding and must not fork the compiler or theme.

### 7.2 Embedding workflow

- Add a build helper that compiles a semantic fixture, writes the required SVG or PNG, and inserts it into an existing Folio `<figure>` or slide image slot.
- Keep generated sources traceable through kind, fixture digest, profile, and artifact digest metadata.
- Fail when the host file references a missing or stale diagram artifact.
- Do not turn Folio into a general HTML or PPTX editor; integrate only through existing document and slide build paths.

### 7.3 Captions and accessible data fallback

- Require insight-led figure captions for document embeds.
- Emit a structured data summary for every data visualization.
- Provide an accessible table fallback for chart data in HTML/PDF reading order without duplicating visible chart labels.
- Validate title, description, language, logical reading order, contrast, table headers, and caption association.

### 7.4 Integration fixtures

- Add one A4 long-document fixture with a structural diagram and one data chart.
- Add one Letter fixture, one Chinese fixture, and one seven-slide deck fixture with at least two diagram profiles.
- Test page count, clipping, raster bounds, stale references, metadata, and slide image placement.

### 7.5 V4.1 exit gate

- All four host contracts pass integration fixtures.
- No embedded diagram clips, distorts, or relies on a static minimum width.
- HTML/PDF chart embeds expose an accessible data summary and table fallback.
- Existing document and slide template verification remains green.
- Standard full release gate passes.

## 8. V4.2 — Data Viz authoring and annotation expansion

### 8.1 Tabular ingestion

- Add local CSV and TSV ingestion with explicit encoding, delimiter, header, column mapping, missing-value, locale, and type-coercion rules.
- Normalize tabular input into the existing typed chart payload before semantic validation.
- Reject ambiguous numeric/date parsing; never guess decimal separators or date order.
- Block remote resources and spreadsheet formulas from the compiler path.

### 8.2 Chart capabilities

- Bar: add stacked mode with positive/negative stack validation and stable segment ids.
- Bar and Line: add one or more semantic benchmark/reference lines with labels and domain checks.
- Bar, Line, and Candlestick: add bounded annotations anchored to semantic marks or x-domain values.
- Waterfall: add explicit subtotal steps with arithmetic verification.
- Extend locale/unit formatting without changing serialized semantic values.

### 8.3 Preserved boundaries

- One x-axis and one y-axis only.
- No dual-axis charts, 3D marks, rainbow palettes, arbitrary mark coordinates, or user-authored SVG paths.
- Annotation count, length, and collision policies remain type-specific and bounded.
- Missing values and reductions remain explicit in diagnostics and metadata.

### 8.4 V4.2 exit gate

- CSV/TSV fixtures cover UTF-8, CJK, missing, malformed, ambiguous, and large bounded inputs.
- Numerical property tests cover stack sums, reference domains, annotation anchors, and waterfall subtotals.
- Stable semantic mark ids survive category reorder where identity is unchanged.
- Visual and accessible data representations agree exactly.
- Standard full release gate passes.

## 9. V4.3 — Diagram catalog expansion

Each new type follows the established sequence: semantic contract, plan grammar, deterministic layout, scene resolution, type validation, profiles, accessibility, fixtures, catalog entry, documentation, and compatibility tests.

### 9.1 Sequence Diagram

- Model participants, messages, activations, notes, alternatives, loops, and returns with bounded nesting.
- Validate participant references, message order, branch completeness, activation balance, and loop depth.
- Use deterministic lifeline spacing and message-label collision handling.
- Ship first because it reuses graph semantics while exercising ordered interaction layout.

### 9.2 UML Class registry migration

- Preserve current UML Class notation and artifact output while moving its public entrypoint behind the shared registry and `CompilationResult`.
- Keep UML-specific grammar outside the shared renderer.
- Add parity tests against the current generator before retiring the separate public path.

### 9.3 Entity Relationship Diagram

- Model entities, attributes, keys, relationships, optionality, and cardinality.
- Validate references, duplicate attributes, key presence, relationship endpoints, and notation consistency.
- Bound entity and attribute budgets and provide deterministic split/reduction diagnostics for dense schemas.

### 9.4 Conditional Sankey

Sankey starts only after Sequence, UML Class migration, and ER pass one complete release gate. Before implementation, run a go/no-go review against these criteria:

- link values are finite, non-negative, and conserved within declared tolerance;
- deterministic node ordering and crossing minimization are achievable within bounded complexity;
- labels remain readable in all required profiles;
- the single-accent Folio palette can encode flow hierarchy without semantic ambiguity;
- the type adds material explanatory value beyond a waterfall or flowchart.

If any criterion fails, record a no-go decision and keep Sankey outside the supported catalog; the program can still complete with the decision evidence.

### 9.5 V4.3 exit gate

- Sequence, UML Class, and ER compile through the shared registry and pass all standard matrices.
- The former UML public path remains compatible or has a documented, tested deprecation adapter.
- Catalog, docs, schemas, fixtures, package, and registry report the same supported-type count.
- Sankey is either production-backed and fully gated or explicitly closed by an evidence-based no-go record.
- Standard full release gate passes.

## 10. Standard release gate

Every phase must pass all applicable checks:

### 10.1 Functional

- Valid canonical, compact, dense, overflow, CJK, and mixed-language fixtures.
- Invalid schema, reference, vocabulary, numerical, accessibility, and geometry fixtures.
- No `ERROR` diagnostic reaches export.
- No requested artifact remains after a failed compile.

### 10.2 Determinism and visual output

- Two repeated clean runs produce identical normalized payload, semantic ids, scene primitives, reading order, and artifact digests.
- SVG, PNG, and PDF pass every applicable output profile.
- Content bounds, dimensions, clipping, text overflow, and malformed paths are checked after export.
- Visual differences are classified; baseline changes require a reason and approval state.

### 10.3 Compatibility and integration

- V3 public commands and artifacts remain compatible unless a deprecation was explicitly scheduled.
- Registry, schemas, fixtures, catalog, README files, `SKILL.md`, and package contents agree.
- Existing document templates, diagrams, demos, and slide builds remain green.

### 10.4 Repository verification

```bash
python3 -m unittest discover -s tests
python3 scripts/build.py --check
python3 scripts/build.py --sync
python3 scripts/build.py --verify
bash scripts/package-skill.sh
```

Also run `git diff --check` and verify `dist/folio.zip` remains below 5 MB and contains the required functional sources, schemas, fixtures, tests, and documentation.

## 11. Evidence and checkpoints

Maintain one checkpoint row per phase in this document or its phase completion record:

| Field | Required evidence |
|---|---|
| State | Current phase state and checkpoint date |
| Scope completed | Work-package ids and concise outcome |
| Defects | Opened and closed P0/P1/P2 ids |
| Tests | Passing count and added fixture/property/compatibility coverage |
| Visuals | Manifest path, changed baselines, approval reasons |
| Build | `--check`, `--sync`, `--verify`, package result |
| Compatibility | Legacy/public entrypoints exercised |
| Residual risk | Bounded issue, impact, and target phase |
| Next entry | Exact prerequisite for the next executable slice |

Task ids use `<release>/<area>/<short-name>`, for example `V4.0/CLI/JSON-DIAGNOSTICS` or `V4.2/BAR/STACK-INVARIANT`. Defect ids use `AUD4-###` and remain stable from audit through regression test.

## 12. Completed checkpoints

### V3.4 — 2026-08-13

| Field | Evidence |
|---|---|
| State | complete |
| Scope completed | Release audit, dependency diagnosis repair, portable package validation, CI fast/release gates, approved visual baseline, registry-derived catalog validation, compatibility tests, and bilingual release notes |
| Defects | AUD4-001 P1 closed; AUD4-002 P1 closed; AUD4-003 P2 closed; AUD4-004 P2 closed |
| Tests | 145 passed; new doctor, package, baseline, registry, and public CLI compatibility coverage |
| Visuals | `references/fixtures/drawing/catalog-baseline-v3.json`; 14 passed; 0 issues; max changed-channel ratio 0.0 |
| Build | `--check`, `--sync`, `--verify`, and package creation passed |
| Compatibility | Architecture, Flowchart, UML Class artifact, V1/V2 migration, schema validation, bundle, render, review, document, diagram, and slide paths passed |
| Residual risk | Hosted workflow awaits the first repository push; local workflow syntax and every constituent command passed |
| Next entry | Inventory runtime validation fields and published schema coverage for all fourteen registered types |

Detailed evidence is in `drawing-dsl-v3-4-audit.md`; release notes are in `../RELEASE_NOTES_V3.4.md`.

### V4.0 — 2026-08-13

| Field | Evidence |
|---|---|
| State | complete |
| Scope completed | Fourteen detailed schemas, minimal/canonical examples, schema registry, migrations, list/init/validate/render/batch CLI, stable diagnostics, atomic output, and authoring guide |
| Defects | AUD4-005 P1 closed; AUD4-006 P1 closed; AUD4-007 P2 closed; AUD4-008 P2 closed; AUD4-009 P1 closed |
| Tests | 159 passed; `jsonschema` 4.23.0 parity run completed without skips |
| Matrix | 126 SVG/PNG/PDF profile artifacts passed; deterministic 14-item batch replay produced identical reports and digests |
| Visuals | 14 approved page-preview baselines passed exactly; max changed-channel ratio 0.0 |
| Build | doctor, `--check`, `--sync`, `--verify`, package creation, package content inspection, and source hygiene passed |
| Package | `dist/folio.zip`, 2,014,950 bytes, 263 files |
| Residual risk | Hosted workflow awaits repository push; local YAML and every constituent command passed |
| Next entry | Audit current document figure and slide image-slot behavior before defining host contracts |

Detailed evidence is in `drawing-dsl-v4-0-audit.md`; release notes are in `../RELEASE_NOTES_V4.0.md`.

### V4.1 — 2026-08-13

| Field | Evidence |
|---|---|
| State | complete |
| Scope completed | Four immutable host contracts, atomic named-slot HTML/PPTX embedding, content-addressed artifacts, source manifests, exact chart data fallbacks, stale/tamper verification, integration fixtures, and public CLI workflows |
| Defects | AUD4-010 P1 closed; AUD4-011 P1 closed; AUD4-012 P1 closed; AUD4-013 P2 closed; AUD4-014 P2 closed; AUD4-015 P1 closed; AUD4-016 P1 closed |
| Tests | 168 passed; new host contract, placement, atomicity, stale source, tamper, accessibility, CLI, and product integration coverage |
| Products | A4 long document 2 pages; Letter document 1 page; Chinese A4 1 page; 16:9 deck 7 slides with two profiles |
| Visuals | 14 approved page-preview baselines passed exactly; max changed-channel ratio 0.0 |
| Build | doctor, `--check`, `--sync`, `--verify`, workflow YAML, package creation, package inspection, and source hygiene passed |
| Package | `dist/folio.zip`, 2,041,746 bytes, 274 files |
| Compatibility | Existing document, diagram, artifact, slide, V3 CLI, V4.0 authoring, registry, profile, and package entrypoints remained green |
| Residual risk | Hosted workflow awaits repository push; local YAML and every constituent command passed |
| Next entry | Audit current data-chart parsing, normalization, validation, formatting, mark identity, and accessible-data behavior before adding CSV/TSV or annotations |

Detailed evidence is in `drawing-dsl-v4-1-audit.md`; release notes are in `../RELEASE_NOTES_V4.1.md`.

### V4.2 — 2026-08-14

| Field | Evidence |
|---|---|
| State | complete |
| Scope completed | Safe local CSV/TSV normalization, explicit locale/value formatting, stacked Bar, Bar/Line references, Bar/Line/Candlestick annotations, Waterfall subtotals, accessible-plan alignment, and public CLI/docs |
| Defects | AUD4-017 P1 closed; AUD4-018 P1 closed; AUD4-019 P1 closed; AUD4-020 P1 closed; AUD4-021 P1 closed; AUD4-022 P2 closed; AUD4-023 P2 closed; AUD4-024 P2 closed; AUD4-025 P2 closed; AUD4-026 P1 closed |
| Tests | 187 passed; tabular ambiguity/security/resource, numerical invariant, stable identity, annotation, subtotal, format, accessibility, schema, CLI, and compatibility coverage |
| Matrix | 36 V4.2 feature artifacts and the canonical 126-artifact matrix passed |
| Determinism | Two imports and two four-fixture batches produced six exact matching outputs and reports |
| Visuals | Only Line changed against the old baseline: classified ratio 0.000272 for axis-position/identity correctness; refreshed 14-type baseline passes exactly |
| Build | doctor, `--check`, `--sync`, `--verify`, workflow YAML, package creation, package inspection, and source hygiene passed |
| Package | `dist/folio.zip` remains below 5 MB with all V4.2 functional sources and evidence included |
| Compatibility | Existing typed 3.0 inputs, registry, three profiles, five chart kinds, host workflows, and public CLI remain green |
| Residual risk | Hosted workflow awaits repository push; local YAML and every constituent command passed |
| Next entry | Audit standalone UML Class, sequence/ER notation, shared compiler boundaries, and Sankey feasibility before expanding the public registry |

Detailed evidence is in `drawing-dsl-v4-2-audit.md`; release notes are in `../RELEASE_NOTES_V4.2.md`.

### V4.3 — 2026-08-14

| Field | Evidence |
|---|---|
| State | complete |
| Scope completed | Sequence, coordinate-free UML Class migration, ER Diagram, shared notation layout/text gates, registry/schema/catalog/CLI/host/package/docs expansion, and Sankey no-go ADR |
| Defects | AUD4-027 P1 closed; AUD4-028 P1 closed; AUD4-029 P1 closed; AUD4-030 P2 closed; AUD4-031 P2 closed; AUD4-032 P2 closed; AUD4-033 P1 closed; AUD4-034 P1 closed; AUD4-035 P2 closed |
| Tests | 198 passed; 3 dependency-conditional skips; semantic identity, route crossing, density, text fit, nullable keys, profiles, formats, host, CLI, package, and legacy compatibility covered |
| Matrix | 153 canonical artifacts passed: 17 kinds × 3 profiles × SVG/PNG/PDF |
| Determinism | Two independent 17-fixture minimal batches produced identical reports and SVG digests |
| Visuals | 17 approved page-preview baselines passed exactly after manual review of Sequence, UML Class, and ER Diagram |
| Build | doctor, `--check`, `--sync`, full `--verify`, package creation, package inspection, JSON/YAML parsing, and source hygiene passed |
| Package | `dist/folio.zip` remains below 5 MB and includes all V4.3 runtime, schemas, fixtures, ADR, tests, docs, and release evidence |
| Compatibility | Existing fourteen types, legacy UML facade, V2/V3 commands, document/slide templates, artifact builds, and four host products remain green |
| Residual risk | Hosted CI awaits repository push; local workflow constituents and full release gates pass |
| Next entry | Treat new work as a separately audited maintenance or V4.4 program; do not reopen the completed V3.4–V4.3 train implicitly |

Detailed evidence is in `drawing-dsl-v4-3-audit.md`; release notes are in `../RELEASE_NOTES_V4.3.md`.

## 13. Active executable slice

No execution slice remains active. The completed checkpoint is `V4.3/RELEASE/COMPLETE`; future work begins with a new audit and explicit release scope.

## 14. Final definition of done

The continuous program is complete when V3.4 and V4.0 through V4.3 have passed their exit gates; Sequence, UML Class, and ER are production registry compilers; Sankey has either passed the same bar or has a recorded no-go decision; every supported type has an authoritative schema, examples, deterministic profiles, accessible artifacts, catalog coverage, and package coverage; document and slide integration passes; no P0/P1 remains open; and the final clean full release gate succeeds without unclassified visual differences or compatibility regressions.
