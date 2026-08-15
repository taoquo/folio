# Folio Drawing DSL V4.2 Data Visualization Audit

Status: complete  
Audit date: 2026-08-13  
Completion date: 2026-08-14  
Scope: tabular authoring, chart semantics, annotations, and formatting

## 1. Current-state inventory

The current Data Viz Core compiles Bar, Line, Donut, Candlestick, and Waterfall payloads directly from typed JSON. It owns finite-number validation, missing-value reduction, deterministic scales, mark geometry, stable SVG primitives, reading order, scene descriptions, and host-accessible data. There is no local CSV/TSV normalization boundary and no current grammar for stacked bars, reference lines, mark annotations, or waterfall subtotals.

| Layer | Current behavior | V4.2 boundary |
|---|---|---|
| Authoring | Typed JSON only | Add an explicit local tabular import step that emits existing typed chart JSON before compilation. |
| Parsing | Python JSON values are validated at runtime | CSV/TSV must declare encoding, delimiter, header mode, mapping, missing tokens, locale, and coercion. |
| Identity | Bar uses series plus category hash; Line uses series plus array index | Every semantic mark must retain identity across category reorder. |
| Scale/layout | One x-axis and one y-axis with fixed 960×540 geometry | Preserve single-axis, deterministic, coordinate-free authoring. |
| Accessibility | Host tables are derived from normalized compiler input | Tables must derive from effective plan semantics after ordering and missing-value reduction. |
| Formatting | Locale selects a compact Chinese or default English formatter; unit placement is implicit | Add bounded explicit formatting without changing serialized numerical values. |

## 2. Findings

| Finding | Severity | State | Evidence and required action |
|---|---|---|---|
| AUD4-017 | P1 | closed | Host fallback data now derives from the effective compiled plan after Bar ordering and Line missing-value reduction, so visible and accessible values agree. |
| AUD4-018 | P1 | closed | Line layouts now own exact ordinal/temporal x positions and pass those coordinates to axis labels. |
| AUD4-019 | P1 | closed | Line categories are unique and point ids derive from series plus category hashes, preserving mark identity across reorder. |
| AUD4-020 | P1 | closed | Negative grouped Bar labels resolve beside the negative endpoint; stacked mode uses explicit positive/negative endpoint totals. |
| AUD4-021 | P1 | closed | All five detailed chart schemas and runtime contracts now require the actual 960×540 compiler canvas and direct users to profiles/hosts for resizing. |
| AUD4-022 | P2 | closed | Waterfall validates `start`, `tolerance`, contributions, subtotals, and end prerequisites before arithmetic and preserves specific WF diagnostics. |
| AUD4-023 | P2 | closed | Locale, unit, source, title, ids, labels, reference labels, and annotation text are bounded; supported locales and explicit display formatting are schema/runtime aligned. |
| AUD4-024 | P2 | closed | The local CSV/TSV importer and CLI require every parse decision, cap bytes/rows/columns, and reject remote paths, formula-like cells, ambiguous values, duplicate headers, and missing mappings. |
| AUD4-025 | P2 | closed | Type-owned plans now implement separate-sign stacked bars, bounded reference lines, semantic Bar/Line/Candlestick annotations, and arithmetically verified Waterfall subtotals. |
| AUD4-026 | P1 | closed | Initial stacked Bar rendering placed segment labels before later segments, hiding intermediate labels and making the visible top label look like a total. Stacked mode now emits only positive/negative endpoint totals while exact segment values remain in the accessible table. |

No P0 was found. All six P1 findings are closed. The remaining work is the complete V4.2 release gate and checkpoint record.

## 3. Implementation sequence

1. Repair AUD4-017 through AUD4-022 with focused positive, negative, identity, and accessibility tests.
2. Introduce bounded locale/unit formatting shared by the four V4.2 chart contracts.
3. Add the local tabular importer, config schema, public CLI, fixtures, ambiguity/formula/resource limits, and deterministic replay tests.
4. Add stacked Bar layout with separate positive and negative accumulators and stable segment ids.
5. Add Bar/Line reference lines with finite values, unique ids, labels, and scale-domain checks.
6. Add bounded Bar/Line/Candlestick annotations anchored only to semantic marks or declared x-domain values.
7. Add Waterfall subtotal steps that verify their declared running total without changing arithmetic.
8. Synchronize detailed schemas, the aggregate V3 compatibility schema, minimal/canonical examples, host fallbacks, documentation, and CLI metadata.
9. Run numerical/property coverage, complete tests, 126-artifact matrix, host products, approved visual comparison, full builds, and package verification.

## 4. Preserved constraints

- One x-axis and one y-axis only.
- No dual axes, 3D marks, rainbow palettes, arbitrary mark coordinates, remote data, formulas, or user-authored SVG paths.
- Serialized semantic numbers remain unchanged by display formatting.
- Annotation count, text, target, and collision behavior are bounded and deterministic.
- Any ambiguous parse, arithmetic mismatch, missing target, or unsupported locale fails closed before artifact output.

## 5. Exit gate

V4.2 completes only when every AUD4-017 through AUD4-025 item is closed; UTF-8, UTF-8 BOM, CJK, missing, malformed, ambiguous, formula, remote, duplicate-header, and bounded-large tabular fixtures pass; stack sums, reference domains, stable identities, annotation targets, and subtotal arithmetic have regression/property coverage; visual and accessible data agree exactly; and the standard full release gate passes with classified visual evidence.

## 6. Release-gate evidence

| Gate | Evidence |
|---|---|
| Findings | AUD4-017 through AUD4-026 are closed; no P0 or P1 remains open. |
| Tests | 187 discovered tests pass with the CI dependency path active. |
| Tabular input | CSV, TSV, UTF-8, UTF-8 BOM, CJK, header/headerless, explicit indexes, missing/null, malformed, ambiguous, formula, remote, duplicate-header, four chart mappings, and 1,000-row bounds are covered. |
| Numerical invariants | Separate positive/negative stack domains, stable reorder ids, reference domains, annotation targets, Line reductions, OHLC fields, Waterfall subtotals, and exact fallback values have positive and negative coverage. |
| Feature matrix | Four maintained V4.2 fixtures pass all three profiles and SVG/PNG/PDF, producing 36 verified feature artifacts. |
| Full matrix | The existing fourteen-kind × three-profile × three-format gate remains green with 126 canonical artifacts. |
| Determinism | Two independent tabular imports and four-fixture SVG batches produced six exact matching files and reports. |
| Accessibility | Host tables derive from effective plans after Bar order and Line reduction; annotations/reference values enter descriptions and stable reading order; Waterfall subtotal rows preserve exact running totals. |
| Visual review | Stacked Bar, annotated Line, annotated Candlestick, and subtotal Waterfall review PNGs passed manual inspection after the stacked-total correction. |
| Visual baseline | Old-baseline comparison changed only Line: stable ids, SVG digest, and a classified 0.000272 pixel-channel ratio. The correction was approved; the refreshed baseline passes all fourteen types exactly. |
| Templates and hosts | Thirty-template `--check`/`--sync` and A4, Letter, Chinese A4, and seven-slide host verification pass. |
| Full artifacts | `build.py --verify` passes every document, diagram, artifact, slide, and host-integration target. |
| CI and hygiene | Workflow YAML parses; fast gate includes Data Viz/tabular tests and CLI import; `git diff --check` passes. |
| Package | `dist/folio.zip` is below 5 MB and includes the importer, schema, fixtures, tests, audit, and authoring documentation. |

## 7. Compatibility and next entry

Existing V3 typed inputs retain schema version `3.0`; all new fields are optional. The aggregate V3 schema, detailed schemas, compiler registry, output profiles, host workflows, package, and public CLI remain compatible. The fixed 960×540 semantic canvas is now explicit; responsive sizing belongs to output profiles and host contracts.

V4.3 may begin with a registry-expansion audit. It must inventory the current standalone UML Class generator, shared compiler grammar boundaries, sequence semantics, ER notation requirements, and Sankey feasibility before adding new public kinds.
