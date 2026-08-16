# Drawing DSL V5 Final Audit

Scope: the V5 program closed all three stages. Stage 1 hardened the V4.3 surface, stage 2 shipped semantic routing across every kind, and stage 3 added five new kinds, external import, theme profiles, output knobs, and render variants.

## Completion matrix

| Stage | Item | State | Evidence |
|---|---|---|---|
| 1-E | Doc version drift 17 -> 22 kinds | Done | `references/drawing-dsl.md`, `references/diagrams.md`, `SKILL.md`, `CHEATSHEET.md` all list 22 |
| 1-F | Visual baseline refresh | Done | `assets/diagrams/generated/catalog/{svg,png,pdf}` 22 files each |
| 1-G | Low-utilization layout review | Done | all 22 catalog kinds reach content/canvas utilization >= 0.6 |
| 1-H | Final acceptance | Done | this document |
| 2 | Semantic pattern routing, 8 patterns | Done | `tests.test_drawing_semantics_route`, `route-diagram` CLI, `references/schemas/route-request.schema.json` |
| 3A | 5 new kinds: pyramid, org-chart, loop-flywheel, scatter, gantt | Done | `references/fixtures/v5/*.json`, catalog count 22 |
| 3B | Mermaid + draw.io import, fidelity ledger | Done | `scripts/drawing/importers/`, `tests.test_drawing_import` |
| 3C-1 | Theme profiles folio / dark / terminal with WCAG gate | Done | `scripts/drawing/theme/`, `tests.test_drawing_theme_v5` (19 assertions) |
| 3C-2 | Output knobs size / detail / audience | Done | `scripts/drawing/output/knobs.py`, `tests.test_drawing_knobs_v5` (10 tests) |
| 3C-3 | Render variants plain / sketchy / motion | Done | `scripts/drawing/output/variants.py`, `tests.test_drawing_variants_v5` (13 tests) |

## Test evidence

| Check | Result |
|---|---|
| 26-module regression | `Ran 284 tests` -> `OK (skipped=3)` in 141s |
| `build.py` | exit 0, zero error lines |
| `build.py --check` | `OK: no violations across 30 templates` |
| `build.py --sync` | `OK: tokens in sync across 30 template(s)` |
| `build.py --verify` | exit 0, zero error lines |
| `package-skill.sh` | `dist/folio.zip` 2.47MB, includes `scripts/drawing/output/variants.py` |
| 22 kinds x 3 themes x 3 details x 3 audiences | 594 combinations, `TOTAL 0` diagnostics |
| 22 kinds x 3 variants | 66 SVG, `BAD 0` marker and payload checks |
| Export widths | compact 1280x720, standard 1920x1080, wide 2560x1440 |
| Degradation warnings | both `page-preview` size warning and `motion` static-export warning fire |

## Artifacts

| Path | Content |
|---|---|
| `assets/diagrams/generated/catalog/svg` | 22 catalog SVG |
| `assets/diagrams/generated/catalog/png` | 22 catalog PNG |
| `assets/diagrams/generated/catalog/pdf` | 22 catalog PDF |
| `references/fixtures/drawing/catalog-baseline-v3.json` | geometry baseline |
| `dist/folio.zip` | packaged skill |

## Reproduction

```bash
python3 scripts/build.py
python3 scripts/build.py --check
python3 scripts/build.py --sync
python3 scripts/build.py --verify
bash scripts/package-skill.sh

python3 -m unittest tests.test_drawing_knobs_v5 tests.test_drawing_variants_v5 \
  tests.test_drawing_theme_v5 tests.test_drawing_quality_v5 tests.test_drawing_dsl_v3 \
  tests.test_drawing_dsl tests.test_drawing_dataviz_v4 tests.test_drawing_notation_v4 \
  tests.test_drawing_hosting tests.test_diagram_catalog tests.test_diagram_export \
  tests.test_drawing_v3_profiles tests.test_drawing_v3_gate_s tests.test_diagram_render_svg \
  tests.test_folio_cli tests.test_drawing_dsl_v2 tests.test_drawing_host_integration \
  tests.test_drawing_schema_registry tests.test_drawing_tabular tests.test_drawing_import \
  tests.test_diagram_geometry tests.test_diagram_layout tests.test_diagram_models \
  tests.test_diagram_semantic_planning tests.test_drawing_semantics_route tests.test_build

python3 scripts/folio.py render-drawing references/fixtures/v3/bar-chart.json \
  --profile artifact --format png --size compact --detail essential \
  --audience executive --variant sketchy --output /tmp/bar.png
```

## Remaining limits

These are known, documented, and non-blocking.

- `references/fixtures/minimal/uml-class.json` reports two TASTE diagnostics under the `artifact` profile: `VQ101` utilization 2.4% and `VQ102` margin 69.6%. It is a minimal contract fixture, not one of the 22 catalog kinds.
- `scripts/diagram_catalog.py` and `scripts/build.py` render with the default `folio` theme and `plain` variant. Knobs and variants are wired only into `render-drawing` and `batch-render-drawings`.
- `scripts/drawing/review.py:write_review_bundle` has no theme or variant parameter, so review bundles are always folio / plain.
- `scripts/drawing/hosting.py` and `scripts/drawing_host_integration.py` embed with the default theme. Host verification compares digests, so a themed embed would need its own baseline before this is opened up.
- `motion` cannot be verified visually in a static pipeline. The test asserts CSS presence plus byte-identical PNG degradation instead.
- `sketchy` filter rendering depends on the rasterizer. It is confirmed under `rsvg-convert`; other renderers may vary in displacement amplitude.

## Invariants preserved

Single accent survives every knob and variant combination, per ADR 0006. Presentation controls stay in the render layer, per ADR 0008. Detail filtering rewrites `reading_order` in the same pass, so `AX200`-`AX203` hold across all 594 verified combinations.
