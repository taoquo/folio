# Folio Drawing DSL V4 Final Program Audit

Status: complete  
Audit date: 2026-08-14  
Scope: V3.4 and V4.0 through V4.3

## Outcome

The continuous release train is complete. Folio now has seventeen production compiler kinds with exact compiler/schema/catalog parity, deterministic SVG/PNG/PDF profiles, document and slide host contracts, approved visual evidence, and a release package below 5 MB. No P0, P1, or accepted P2 finding remains open in the active V4 audits.

## Final evidence

| Gate | Result |
|---|---|
| Runtime contracts | 17 compiler keys equal 17 schema contracts and 17 catalog entries. |
| Authoring | Every kind has an authoritative schema, minimal fixture, canonical fixture, migration version, CLI discovery, initialization, validation, and rendering path. |
| Output | 153 canonical combinations passed: 17 kinds × 3 profiles × SVG/PNG/PDF. |
| Determinism | Two independent 17-fixture minimal batches produced identical reports and SVG SHA-256 digests. |
| Accessibility | Every SVG carries title, description, language, stable reading order, and semantic ids; data hosts retain exact fallback tables or notes. |
| Host integration | A4, Letter, responsive HTML, and 16:9 contracts pass fit, traceability, stale/tamper, caption, alt-text, and artifact verification. |
| Tests | 198 passed; 3 dependency-conditional skips; no failure. |
| Visual | 17 approved page-preview baselines pass exact comparison with no unclassified change. |
| Build | Dependency doctor, template check, token sync, full target verification, workflow YAML parsing, JSON parsing, and source hygiene pass. |
| Package | Final `dist/folio.zip` remains below 5 MB and includes all required V4.3 runtime, schema, fixture, test, ADR, audit, documentation, and release-note sources. |

## Defect closure

- V3.4: AUD4-001 through AUD4-004 closed.
- V4.0: AUD4-005 through AUD4-009 closed.
- V4.1: AUD4-010 through AUD4-016 closed.
- V4.2: AUD4-017 through AUD4-026 closed.
- V4.3: AUD4-027 through AUD4-035 closed.

The final V4.3 pass additionally fixed overwritten notation semantic ids, route crossings through unrelated items, duplicate route points, missing relationship metrics, text and density overflow, malformed member diagnostics, and nullable primary keys.

## Compatibility and residual risk

Existing fourteen-type behavior, V2/V3 commands, expert Architecture input, legacy UML loading/rendering, document templates, slide templates, five standalone diagram artifact builds, and four host products remain green. Sankey is deliberately outside the registry under ADR 0007.

The only operational residual is that hosted CI cannot execute until repository changes are pushed. The workflow parses locally and all constituent fast and release commands pass. Any future feature work starts as a new audited release scope rather than extending this completed program implicitly.
