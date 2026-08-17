# Folio Drawing DSL Authoring Guide

Folio authoring input describes meaning, relationships, focus, and evidence. It never describes pixels. Start with the diagram's communication job, choose the narrowest registered type, and supply only the semantic data required by that type.

## 1. Discover a contract

```bash
python3 scripts/folio.py list-diagram-types
python3 scripts/folio.py list-diagram-types --format json
```

The list is derived from the production compiler and schema registries. Each record identifies the input schema version, authoritative schema, minimal and canonical examples, output profiles, and export formats.

## 2. Start from a minimal input

```bash
python3 scripts/folio.py init-drawing timeline --output /tmp/timeline.json
python3 scripts/folio.py init-drawing bar-chart --language zh-CN --output /tmp/bar.json
```

The generated JSON is intentionally neutral. Replace the placeholder title, ids, labels, dates, and values with real content. Do not add coordinates, colors, font sizes, paths, or rendering instructions.

Every registered type has two maintained examples:

- `references/fixtures/minimal/<kind>.json` proves the smallest useful compiling shape.
- The `canonical_fixture` returned by `list-diagram-types --format json` demonstrates normal production use.

## 3. Validate before rendering

```bash
python3 scripts/folio.py validate-drawing /tmp/timeline.json
python3 scripts/folio.py validate-drawing /tmp/timeline.json --format json
```

Validation uses the same compiler boundary as rendering. JSON diagnostics are sorted deterministically and contain `code`, `severity`, `stage`, `kind`, `path`, `message`, `hint`, and `related_ids`.

Exit codes are stable:

| Code | Meaning |
|---:|---|
| 0 | Valid input or successful operation |
| 1 | Invalid authoring input |
| 2 | Missing dependency or file/export operation failure |
| 3 | Internal Folio command failure |

## 4. Import local CSV or TSV data

Use the tabular importer when chart values start in a local delimited file:

```bash
python3 scripts/folio.py import-chart-data \
  references/fixtures/tabular/bar-import.json --output /tmp/bar.json
python3 scripts/folio.py validate-drawing /tmp/bar.json
```

The config contract is `references/schemas/tabular-chart-import.schema.json`. It requires an explicit local path, CSV/TSV format, UTF-8 encoding, one-character delimiter, header mode, column mapping, missing tokens and policy, locale, strict decimal separators, and ISO date coercion. Relative paths resolve from the config file. The importer supports Bar, Line, Candlestick, and Waterfall, emits ordinary compiler-ready `3.0` JSON, and never reads remote resources.

Imports fail closed on duplicate headers, unknown columns, ragged rows, unsupported encodings/locales, ambiguous decimal or thousands separators, non-ISO dates, formula-like cells, files over 2 MB, more than 64 columns, or more than 1,000 data rows. Missing numerical values may normalize to `null` only for Line; the compiled `missing_policy` still decides whether those values become gaps, zeroes, carry-forward values, or errors.

## 4b. Import Mermaid or draw.io diagrams

Use the diagram importer when a structural diagram already exists in Mermaid or draw.io form:

```bash
python3 scripts/folio.py import-diagram references/fixtures/import/flowchart.mmd \
  --output /tmp/flow.json --ledger-output /tmp/flow-ledger.json
python3 scripts/folio.py validate-drawing /tmp/flow.json
```

`--dialect` defaults to `auto` and resolves only from the file suffix: `.mmd` / `.mermaid` -> `mermaid`, `.drawio` / `.xml` -> `drawio`. Pass `--dialect` explicitly for any other suffix. Supported Mermaid headers are `flowchart` / `graph`, `sequenceDiagram`, `stateDiagram(-v2)`, `erDiagram`, and `classDiagram`; draw.io import covers single-page flowcharts.

Every import emits a fidelity ledger described by `references/schemas/diagram-import-ledger.schema.json`. The ledger separates `preserved`, `downgraded`, and `dropped` features and reports `fidelity` as the preserved share. Review it before shipping an imported diagram: coordinates, subgraphs, styling, notes, self-messages, and sequence blocks are intentionally dropped because Folio recomputes deterministic layout.

| Source feature | Import result |
|---|---|
| Mermaid `-.->` / draw.io `dashed=1` | `exception-flow` edge, recorded as a downgrade |
| Mermaid edge label | `conditional-flow` edge carrying the label |
| Mermaid `stateDiagram` without a `[*]` exit | `persistent: true`, recorded as a downgrade |
| Mermaid ER entity without `PK` | first field promoted to primary key, recorded as a downgrade |
| Mermaid class `<<interface>>` / `<<enumeration>>` | type kind becomes `interface` / `enum` |
| draw.io geometry, swimlanes, groups, notes | dropped; Folio recomputes layout |

Imports fail closed on remote paths or URL schemes, missing files, sources over 512 KB, unsupported headers, more than 12 nodes or 24 edges, compressed draw.io payloads, multi-page draw.io files, and invalid XML. Split large source diagrams before importing instead of relaxing the budgets.

## 5. Render one drawing

```bash
python3 scripts/folio.py render-drawing /tmp/timeline.json \
  --profile artifact --format svg --output /tmp/timeline.svg
```

Profiles are `artifact`, `embed`, and `page-preview`. Formats are `svg`, `png`, and `pdf`. Rendering validates first and writes the final artifact atomically, so invalid input cannot leave a partial output.

## 6. Render a deterministic batch

```bash
python3 scripts/folio.py batch-render-drawings references/fixtures/minimal \
  --output-dir /tmp/folio-batch --format svg \
  --report-format json --report-output /tmp/folio-batch-report.json
```

Directory inputs are processed in stable relative-path order. Output names combine a readable relative-path slug with a stable path digest, preventing collisions between same-named files in different directories. Invalid items produce no artifact. The aggregate exit code is non-zero when any item fails; `--fail-fast` stops after the first failure.

## 7. Contract ownership

The authoritative type schemas live in `references/schemas/types/`. JSON Schema owns field names, required fields, scalar types, enums, collection budgets, and unknown-field rejection. The production compiler additionally owns graph references, reachability, ordering, arithmetic conservation, focus limits, geometry, accessibility, and editorial quality diagnostics.

Architecture semantic input is version `3.0`; legacy unversioned semantic payloads migrate deterministically to `3.0`. Expert-authored Architecture `DrawingPlan` input remains on its compatible `2.0` contract. Flowchart remains on input version `2.0`. All other current registered inputs use `3.0`.

An explicit `null` on an optional field means the same thing as omitting it, so every optional property accepts `null` in both the schema and the compiler. A blank or non-string value is still rejected. `tests/test_drawing_schema_registry.py` cross-checks the two sides for every optional field of every kind, so the schema can no longer drift from the runtime.

A missing required field is rejected by both sides as well, with one deliberate exception: Architecture backfills `schema_version` for legacy unversioned semantic payloads. The same registry test asserts the rejection for every other required field of every kind.

### Canvas contract

Every payload declares the same 960-unit stage width, and `height` is the only canvas knob. The bounds come from one shared module, `scripts/drawing/canvas_contract.py`, so a family cannot quietly introduce its own floor.

| Family | Kinds | Width | Height band | Default |
|---|---|---|---|---|
| Graph | architecture, flowchart, state-machine, swimlane, tree, layer-stack, timeline, quadrant, venn, pyramid, org-chart, loop-flywheel | `960` exactly | 500-800, step 4 | 540 |
| Chart | bar-chart, line-chart, donut-chart, candlestick, waterfall, scatter, gantt, heatmap | `960` exactly | 400-720, step 4 | 540 |
| Notation | sequence, uml-class, er-diagram | `960` exactly | 480-800, step 4 | 640 (sequence 540) |

An off-grid or out-of-band height is an `ERROR`, not a silent clamp: `<kind> canvas height must be a multiple of 4 from <min> to <max>`. A width other than 960 reports `use an output profile to rescale`, because responsive sizing belongs to `--size` and the host contract, never to the payload.

Two compiler-owned exceptions stay adaptive after validation. Flowchart fits the stage to its widest row, so its scene width can land below 960 and its height only grows. State machine derives height from its layer count when the payload omits `height`. Both still validate any height you declare against the graph band.

On loop-flywheel, quadrant, and venn the radial geometry is not height-derived, so the knob validates but does not move the drawing.

## 8. Data visualization expansion

- Bar supports `mode: grouped|stacked`; stacked mode keeps positive and negative accumulators separate.
- Bar and Line accept up to three `reference_lines`, each with a stable id, short label, finite value, and enforced data-domain placement.
- Bar, Line, and Candlestick accept up to three semantic `annotations`; targets use series/category or period/field identity, never coordinates.
- Waterfall contribution `kind` is `delta` by default or `subtotal`; a subtotal value must equal the current running total within `tolerance` and does not alter arithmetic.
- `value_format` controls precision, compact notation, grouping, and unit position for display only. Semantic and accessible values remain exact.
- Supported locales are `en-US`, `en-GB`, `zh-CN`, and `zh-TW`. The chart canvas follows the shared contract in section 7: width fixed at 960, `height` a bounded knob accepting 400-720 in steps of 4, defaulting to 540.
- Heatmap accepts 3-12 `columns` (labels up to 12 characters) and 3-10 `rows`; every row needs a stable id, a label, and one finite value per column. Cells carry no numeric text: the graded intensity legend and the accessible description own the values, which keeps contrast safe on every theme.
- Heatmap grades one measure with a single warm ramp and allows at most one `emphasis: focal` row, rendered in the accent color. Multi-hue colormaps are out of scope.

Maintained feature examples live under `references/fixtures/v4/`.

## 9. Notation diagrams

- Sequence accepts 2-6 `participants` and 1-12 ordered `messages`; participant kinds are `actor`, `system`, or `store`, and message kinds are `sync`, `async`, or `return`.
- UML Class accepts 1-8 `types` and up to 12 `relationships`; type kinds are `class`, `interface`, or `enum`, and relationship kinds are `inheritance`, `association`, `aggregation`, or `composition`.
- ER Diagram accepts 2-8 `entities`, 1-8 fields per entity, and 1-12 cardinality-bearing `relationships`. Every entity requires a primary key.
- Every semantic object and relationship requires a stable id. UML and ER reject duplicate directed endpoint pairs so parallel relations cannot collapse into one route.
- Do not add `x`, `y`, box dimensions, connector paths, marker definitions, or colors. The compiler owns geometry and manual arrowheads.

Start from `references/fixtures/v4/sequence.json`, `uml-class.json`, or `er-diagram.json`. Sankey is not a supported grammar; use Bar or Waterfall for magnitude decomposition and Architecture, Swimlane, or Sequence for interaction flow.

## 10. Authoring boundaries

Use one clear focus, bounded labels, and evidence-backed data. Split a diagram when it exceeds the type budget. Avoid double axes, 3D marks, decorative colors, arbitrary geometry, hidden transformations, or a generic object bag. If the content cannot be expressed without those escapes, improve the type grammar or choose a different diagram type instead of bypassing the compiler.

Parallel edges must stay readable. Architecture, Flowchart, Layer Stack, State Machine, and Swimlane reject a second edge between the same pair when nothing distinguishes it, joining UML and ER in that rule:

| Diagram | Distinguishing fields | Code |
|---|---|---|
| Architecture | `label`, `kind` | `DG042` |
| Flowchart | `label`, `kind` | `FC019` |
| Layer Stack | `label`, `channel` | `LS009` |
| State Machine | `event`, `guard`, `action` | `SM023` |
| Swimlane | `label`, `channel` | `SW020` |

Give each parallel edge its own label or channel, or merge the two into one relation. Labels on parallel edges are exempt from the edge-label budget, so the compiler never drops the text that tells them apart.

## 11. Embed in documents and slides

Discover the four explicit host contracts:

```bash
python3 scripts/folio.py list-drawing-hosts --format json
```

HTML hosts use an exact `<figure data-folio-diagram-slot="slot-id">` placeholder. PPTX hosts use a shape named `folio-diagram-slot:slot-id`. Compile and fill the slot atomically:

```bash
python3 scripts/folio.py embed-drawing references/fixtures/v3/bar-chart.json \
  --host-contract a4-portrait --host-file report.html --output-host report-filled.html \
  --slot coverage --caption "Generator-backed coverage reaches all twenty-three registered types."

python3 scripts/folio.py embed-drawing references/fixtures/v3/line-chart.json \
  --host-contract slide-16x9 --host-file deck.pptx --output-host deck-filled.pptx \
  --slide-index 3 --slot trend \
  --caption "Validation improves at every gate and reaches full coverage."
```

Verify sources, artifact digests, fit, captions, alt text, and data fallback after every host mutation:

```bash
python3 scripts/folio.py verify-drawing-host report-filled.html
python3 scripts/folio.py verify-drawing-host deck-filled.pptx --format json
```

`a4-portrait` and `letter-portrait` embed responsive SVG with the `embed` profile. `responsive-html` uses the same profile without a static minimum width. `slide-16x9` uses a content-addressed PNG at 144 ppi and supports `artifact` or `embed`. Folio always contain-fits the resolved scene and never stretches it.

Every hosted artifact records the kind, normalized registry key, fixture path and digest, profile, artifact path and digest, source dimensions, language, description, caption, placement, and exact accessible data. Data charts emit a compact visible table in HTML/PDF reading order and an equivalent tab-separated block in PowerPoint notes. Any missing or changed fixture, artifact, caption association, table value, notes value, alt text, or aspect ratio fails host verification.

## 12. Theme profiles

Every color a compiler emits comes from a FolioTheme token, so a theme change is a deterministic token-for-token substitution applied to the resolved scene after layout. Geometry, text measurement, reading order, and accessible data are identical across profiles.

| Profile | Canvas | Accent | Use |
|---|---|---|---|
| folio | parchment #F6F0EA | #B83D2E | Default. Print documents and light hosts. |
| dark | warm brown #16120F | #F08A72 | Dark slides, dark web hosts. |
| terminal | green-black #0C1110 | #6BE39B | Engineering and developer contexts. |

Pass `--theme` to any drawing subcommand; it defaults to `folio`:

```bash
python3 scripts/folio.py render-drawing references/fixtures/v3/state-machine.json \
  --profile artifact --format png --theme dark --output /tmp/state-dark.png

python3 scripts/folio.py check-drawing references/fixtures/v3/donut-chart.json --theme terminal

python3 scripts/folio.py batch-render-drawings references/fixtures/v5 \
  --output-dir /tmp/folio-dark --format svg --theme dark
```

Typography tokens are never swapped. Text is measured during layout with the Folio families, so changing a family after layout would invalidate every measured box.

Register a project palette only through the guarded entry point. Registration recomputes WCAG contrast for every token pair the compilers actually paint and rejects any palette that would ship an unreadable diagram:

```python
from drawing.theme import DARK_THEME, contrast_violations, register_theme_profile, with_tokens

palette = with_tokens(DARK_THEME, brand="#F2A18C", brand_tint="#4C2C24")
assert contrast_violations(palette) == ()
register_theme_profile("dark-warm", palette)
```

Contrast rules a palette must satisfy:

- Body text on canvas, card, and accent tint reaches 4.5:1; large or reversed text on a filled shape reaches 3.0:1.
- `muted_stroke`, `neutral_deep`, `brand`, `olive`, and `stone` reach 3.0:1 against the canvas because they paint strokes wider than one pixel.
- `border` is a hairline token. Keep it at `stroke_width <= 1` and never use it as a text color.
- `neutral_mid` and `neutral_light` are fill-only ramp steps. They paint bar, donut, and mark bodies that always ship with an adjacent labeled key, so they are exempt from non-text contrast and must never carry text or a stroke wider than one pixel.

Built-in profiles cannot be removed or shadowed, and an unknown profile name fails closed at both the CLI and the compiler boundary.

## 13. Output knobs and render variants

Theme changes palette. These four knobs change presentation without changing meaning. All of them are output-layer flags on `render-drawing` and `batch-render-drawings`. None of them belongs in a payload: the chart field whitelist rejects unknown keys with `ERROR BC000`.

### Size

`--size compact|standard|wide` maps to a raster export width of 1280 / 1920 / 2560. The resolved scene is identical for all three; only the rasterizer target changes, so a `compact` PNG and a `wide` PNG are the same drawing at different pixel densities. `standard` is the default and matches the existing 1920px profile baselines. `page-preview` ignores `--size` because it renders a fixed A4 raster at 1241x1754, and the CLI prints a warning when you combine them.

### Detail

`--detail essential|standard|full` controls how much supporting scaffolding survives.

| Level | Gridlines | Annotations |
|---|---|---|
| `full` | all | kept |
| `standard` | every other gridline | kept |
| `essential` | none | dropped |

Data is never removed. On a bar chart the bar count is constant across all three levels; only gridlines change (4 / 2 / 0). Filtering rewrites `reading_order` in the same pass, so the accessibility gates `AX200`-`AX203` continue to pass.

### Audience

`--audience executive|general|practitioner` currently has one behavior: `executive` raises any text below 10pt by 1pt, recursively through groups, so a projected slide stays legible from the back of a room. `general` and `practitioner` are pass-through and reserved for later density rules. The bump never adds elements and never touches accent usage.

### Variant

`--variant plain|sketchy|motion` injects a scoped `<defs>` block into the SVG. Geometry, text, ids, and reading order are byte-identical to `plain`; only the defs block and the root `data-folio-variant` attribute differ.

- `sketchy` adds an `feTurbulence` plus `feDisplacementMap` filter applied to shape strokes only. The canvas background carries `data-folio-role="canvas"` and is excluded, and text is never filtered, so labels stay crisp while boxes and connectors gain a hand-drawn wobble.
- `motion` adds a `@keyframes` reveal gated behind `prefers-reduced-motion: no-preference`, staggered by `data-reading-order` at 70ms per step and capped at 700ms. It is CSS-driven, so PNG and PDF exports degrade exactly to `plain` and the CLI warns.

```bash
python3 scripts/folio.py render-drawing references/fixtures/v3/bar-chart.json \
  --profile artifact --format png --size compact --detail essential \
  --audience executive --variant sketchy --output /tmp/bar.png

python3 scripts/folio.py batch-render-drawings references/fixtures/v5 \
  --output-dir /tmp/folio-wide --format svg --size wide --variant motion
```

The batch report records `size`, `detail`, `audience`, and `variant` alongside `theme`, so a rendered directory can always be traced back to the exact flag combination that produced it.

### Themes and variants inside hosts

`embed-drawing` and `review-drawing` accept the same `--theme` and `--variant` flags. The host manifest is schema 1.1 and records both, the generated `<figure>` carries `data-folio-theme` and `data-folio-variant`, and `verify-drawing-host` fails when either drifts from the embedded SVG.

```bash
python3 scripts/folio.py embed-drawing references/fixtures/minimal/tree.json \
  --host-contract a4-portrait --host-file references/fixtures/hosting/a4-long-doc.html \
  --output-host /tmp/host.html --slot structure --theme dark --variant sketchy \
  --caption "The single root keeps the structural hierarchy bounded and immediately scannable."
```

`motion` is accepted for HTML hosts and rejected for PPTX slots, because a rasterised slide image cannot carry a CSS reveal.
