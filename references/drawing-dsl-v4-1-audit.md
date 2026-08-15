# Folio Drawing DSL V4.1 Host Integration Audit

Status: complete  
Audit date: 2026-08-13  
Completion date: 2026-08-13  
Scope: native document and slide integration

## 1. Current-state inventory

Folio currently has A4 HTML templates and 16:9 Python slide templates, but no type-neutral host contract or verified embedding workflow.

| Surface | Current behavior | Gap |
|---|---|---|
| A4 long document | Generic `figure`, `img`, and `figcaption` CSS only | No generated-artifact source trace, slot contract, chart data fallback, or stale check |
| A4 equity report | Two hard-coded chart placeholders instruct authors to extract SVG manually | Bypasses compiler, metadata, artifact verification, and accessibility contract |
| Letter document | Existing templates are A4 only | No explicit Letter page/safe-area host contract or fixture |
| Responsive HTML | Standalone SVG `embed` profile exists | No host slot, caption association, fallback table, or stale-reference verifier |
| 16:9 slides | `add_diagram_png` calls `add_picture` with both caller-supplied width and height | Image aspect ratio can be distorted; no source trace, alt text, caption contract, notes fallback, or stale check |

Current generated SVGs already contain a title, description, language, logical reading order, stable ids, and type-neutral primitives. V4.1 should preserve that compiler boundary and add host-specific fit, traceability, caption, and fallback behavior outside the renderer.

## 2. Findings

| Finding | Severity | State | Required action |
|---|---|---|---|
| AUD4-010 | P1 | closed | Both slide helpers now use type-neutral contain-fit, preserve source aspect ratio, and write alt text. PPTX host verification rejects distortion and stale alt text. |
| AUD4-011 | P1 | closed | Equity-report templates expose named figure slots and no longer instruct manual SVG extraction. `embed-drawing` compiles, writes content-addressed artifacts, embeds atomically, and records portable source metadata. |
| AUD4-012 | P1 | closed | All five data-chart contracts produce exact structured summaries and tables. HTML/PDF use associated visible tables; PPTX uses equivalent notes. Verification compares every header and value with the embedded manifest. |
| AUD4-013 | P2 | closed | Immutable A4 portrait, Letter portrait, 16:9 slide, and responsive HTML contracts own safe areas, fit, density, caption spacing, artifact format, and allowed output profiles. |
| AUD4-014 | P2 | closed | HTML and PPTX manifests record fixture/artifact paths and digests, dimensions, registry key, language, description, caption, data, and placement. Host verification fails on missing or stale inputs/artifacts and runs inside the build gate. |
| AUD4-015 | P1 | closed | Initial host output validation happened after replacing the destination, and mutable filenames allowed older hosts to point at overwritten artifacts. HTML/PPTX now verify temporary hosts before atomic replacement and use content-addressed artifact names. |
| AUD4-016 | P1 | closed | A host manifest could verify its external artifact while the inline SVG, embedded PPTX image, or caption had been altered independently. Verification now hashes the actual embedded SVG/image and compares exact caption, language, description, table, and notes content. |

All audit findings are closed. No P0 or P1 remains open.

## 3. Intended ownership

```text
typed fixture -> existing compiler registry -> CompilationResult
              -> existing SVG/PNG exporters
              -> host contract (fit, safe area, density, caption gap)
              -> explicit HTML figure or PPTX image slot
              -> portable source/artifact manifest
              -> host verifier (caption, fallback, bounds, stale digests)
```

The host layer must not branch on diagram geometry or add drawing semantics. Data fallback generation may branch only on the five registered data contracts because it serializes their semantic values rather than visual marks.

## 4. Release-gate evidence

| Gate | Evidence |
|---|---|
| Tests | 168 discovered tests passed with the CI dependency path active. |
| Host contracts | A4 portrait, Letter portrait, 16:9 slide, and responsive HTML contracts are immutable and registry-backed. |
| Integration products | A4 long document rendered as 2 pages, Letter as 1 page, Chinese A4 as 1 page, and the 16:9 deck as 7 slides. |
| Placement | PDF page-size and raster-bound checks passed; both slide diagrams remained inside their safe areas with preserved aspect ratios. |
| Accessibility | All data-chart hosts expose exact semantic summaries and values through HTML tables or PPTX notes; title, description, language, caption, and alt text are verified. |
| Traceability | Fixture and artifact SHA-256 digests, registry key, profile, dimensions, placement, caption, and semantic data are recorded and revalidated. |
| Atomicity | HTML and PPTX hosts verify in temporary files before atomic replacement; artifacts use content-addressed names. |
| Tamper resistance | Inline SVG, embedded PPTX image, caption, HTML table, PPTX notes, source fixture, and external artifact mutations all fail verification. |
| Determinism | Two independent host builds produced exact non-PPTX source and artifact bytes; normalized host manifests and content-addressed digests remain stable. |
| Visual baseline | Fourteen approved page-preview PNGs passed exact RGBA comparison with maximum changed-channel ratio 0.0. |
| Templates | `build.py --check` and `build.py --sync` passed across thirty templates. |
| Full artifacts | `build.py --verify` passed every document, diagram, artifact, slide, and host-integration target. |
| Package | `dist/folio.zip` rebuilt at 2,041,746 bytes with 274 verified files and all required host sources, fixtures, tests, and documentation. |
| Source hygiene | Workflow YAML parsing and `git diff --check` passed. |

## 5. Compatibility and residual risk

The host layer consumes the existing registry compiler and output profiles; it does not fork geometry, semantic planning, or rendering. Existing document, diagram, artifact, slide, V3 CLI, V4.0 authoring, and package paths remain green.

The hosted GitHub workflow still requires a repository push to run remotely. Its YAML parses locally and every constituent command has passed locally, so no implementation defect remains open.

V4.2 may begin with a data-contract audit. It must inventory current chart parsing, normalization, validation, formatting, mark identity, and accessible-data behavior before adding tabular ingestion or annotations.
