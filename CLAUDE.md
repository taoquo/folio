# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`AGENTS.md` is the canonical project guide. Read it first. It owns the full verification matrix, change rules, release flow, and WeasyPrint pitfalls; this file records the environment specifics and the architecture that spans several modules. If the two disagree, `AGENTS.md` wins.

## Environment

Python 3.10+ is required (`pyproject.toml`). On this machine the default `python3` is 3.9.6 and cannot import the scripts (`TypeError: unsupported operand type(s) for |`), so use the local venv:

```bash
.venv-weasy/bin/python --version   # 3.14.x, dependencies installed
.venv-weasy/bin/python scripts/folio.py doctor
# or: python3.14 ...
```

Install CI dependencies with `python -m pip install -r requirements-ci.txt`. `doctor` checks WeasyPrint native libraries, PDF tools, diagram exporters, PPTX, and Chinese fonts before rendering.

## Commands

Product CLI (stable entry point; it wraps `scripts/build.py`):

```bash
.venv-weasy/bin/python scripts/folio.py doctor
.venv-weasy/bin/python scripts/folio.py list-targets
.venv-weasy/bin/python scripts/folio.py check            # CSS + token checks
.venv-weasy/bin/python scripts/folio.py build resume-en  # one target
.venv-weasy/bin/python scripts/folio.py verify resume-en # build + page count + fonts
.venv-weasy/bin/python scripts/folio.py package          # dist/folio.zip
```

Tests are `unittest`, not pytest, and each module inserts `scripts/` into `sys.path` itself:

```bash
.venv-weasy/bin/python -m unittest discover -s tests
.venv-weasy/bin/python -m unittest tests.test_document_ir -v
.venv-weasy/bin/python -m unittest tests.test_document_ir.TestClass.test_name -v
```

Lint matches CI (`ruff==0.14.5`, config in `pyproject.toml`):

```bash
ruff check .
```

The gates that matter most after a change (`AGENTS.md` has the complete list):

```bash
.venv-weasy/bin/python scripts/build.py --check      # template CSS rules
.venv-weasy/bin/python scripts/build.py --sync       # token drift across templates
.venv-weasy/bin/python scripts/fidelity.py measure   # IR path vs template path
.venv-weasy/bin/python scripts/corpus.py validate
.venv-weasy/bin/python scripts/check_links.py
```

CI has three tiers in `.github/workflows/`: a fast gate on every push/PR (lint, tests, template/colour/corpus checks, a smoke render), a release gate (full corpus, determinism, shadow comparison, package), and a nightly document-engine run. Tests run on Python 3.10, 3.12, and 3.14.

## Architecture

### Two different builds

- `scripts/build.py` renders **templates** to PDF/PPTX. Templates keep their `{{...}}` fields, so the output is a structural example. It also builds diagram artifacts and the generated catalog.
- `scripts/document_build.py` renders **content** to a finished document, through fixtures in `references/fixtures/document/`. `build.py` uses this path for the published examples, sourcing them from `references/fixtures/document/showcase/`.

Do not confuse the two: `--check-placeholders` is meaningful for built documents, not for the template library.

### Document IR

`scripts/document_ir/` is a semantic model with no geometry or style — no font size, colour, margin, or coordinate. A test walks every field against a banned vocabulary; `validate.py` is fail-closed. Pipeline:

```text
fixture / structured content
  -> readers/structured.py        (JSON/YAML -> Document; unknown content -> raw_fallback)
  -> model.py + containers.py     (frozen semantic nodes, declared template containers)
  -> validate.py                  (ids, references, structure)
  -> writers/skeleton.py          (fill the template's own markup; the compatibility path)
     or writers/html.py / pptx.py (standalone document rendering)
  -> WeasyPrint adapter / PPTX
```

`writers/skeleton.py` is the key design decision: a template's appearance is its DOM shape, not its class names. Rebuilding the markup from a flat block list scored SSIM 0.135, so the writer uses the template as the skeleton and the IR only supplies values and stable ids (`data-folio-id`). A template edit can therefore break the writer — rerun `fidelity.py measure`.

`FOLIO_PIPELINE` selects the path: `ir` (default), `ir-shadow` (deliver template output, build IR alongside), `legacy` (template only, kept for rollback). The choice is deliberately reversible by environment variable.

`scripts/projection.py` appends the resolved style and optional layout policy inside the template's existing `<style>` element as CSS variables — the template itself is not edited. `FOLIO_STYLE_PROJECTION`, `FOLIO_LAYOUT_POLICY`, and `FOLIO_BUILD_MANIFEST` control it.

### Style, themes, and page contracts

- `references/profiles/{typography,page,web,language,taste,theme}/` hold the profiles. `scripts/style_resolver.py` combines them and records the origin of every value; `scripts/projection.py` turns the result into CSS.
- A theme file (`references/profiles/theme/*.yaml`) has two layers: `palette` holds each raw colour once by lightness name; `color` holds the roles templates read. `FOLIO_THEME` selects a scheme; unset uses the profile marked `default` (`folio-classic-v1`). Never hard-code a hex in a template.
- `scripts/page_contracts.py` is the single source for page-count contracts. `build.py` enforces them and `stabilize.py` reads them; change them only there.
- `scripts/section_defaults.py` supplies defaults for structural labels promoted to template placeholders, so a template still renders on its own.

### Drawing DSL

`scripts/drawing/` compiles 23 registered diagram types through one registry:

```text
normalized input -> compiler registry -> type semantic IR -> type plan
                 -> deterministic layout (ELK backend) -> ResolvedScene
                 -> canvas / primitive / accessibility validation
                 -> SVG / PNG / PDF output profile
```

- `SemanticDiagram` says what exists; `DrawingPlan` says how meaning is encoded; `ResolvedScene` is the only input the SVG renderer accepts.
- Size, detail, audience, and variant are render-layer knobs (`scripts/drawing/output/`), never payload fields.
- `scripts/drawing/semantics/` is the V5 router (`route-diagram`); it recommends a kind before geometry exists and never writes an artifact.
- The public CLI verbs are `list-diagram-types`, `init-drawing`, `validate-drawing`, `render-drawing`, and `batch-render-drawings`. `diagram-catalog` regenerates the contact sheets and checks the approved baseline.

### Web reading-page scenario

`references/web/` defines a static reading-page scenario (series index + module archive), not an app framework. `scripts/build_web.py` builds a series from `series.json` plus `.frag.html` modules into `dist/web/`; `scripts/check_web.py` and `scripts/web_geometry.py` enforce stable `W-*` rule ids at levels 1–3; `scripts/web_contracts.py` is the shared vocabulary. Templates live in `assets/templates/web/`.

The screen scale is not a second design system. `references/profiles/web/folio-v1.yaml` owns font stacks, px type roles, spacing, radii, measure and page geometry; `projection.web_projection()` emits them; `base.css` reads only custom properties. A literal size, family, spacing value or hex in the template is a defect, and `projection.py check` rejects it. The series language (`series.json` `language`) selects the Chinese or English profile and the chrome strings. Non-goals: components, router, client state, dark-mode switch.

### Generated artifacts

These are build outputs — regenerate, do not hand-edit: `assets/examples/` (gitignored), `assets/diagrams/generated/`, `assets/demos/`, `dist/`, `assets/templates/output.pptx`. The two homepages (`index.html`, `index-zh.html`) and `assets/demos/*.html` have their theme baked in by `scripts/build_static_theme.py`; `--check` fails when they are stale.

## Change rules that cross files

- **Template edit:** rerun `fidelity.py measure`; the skeleton writer may have drifted. Content-only edits should not touch CSS.
- **Diagram template edit:** mirror the geometry into the mini SVG in both homepages; `build.py --check-index` requires byte-identical geometry.
- **Colour change:** edit the theme profile, then `build_color_reference.py --design`, `build.py --sync`, `check_theme_schemes.py`, and `build_static_theme.py`.
- **Page-count change:** edit `scripts/page_contracts.py`, never a consumer.
- **IR change:** no style or geometry may enter the model; run the banned-vocabulary test and `corpus.py validate`.
- **Docs:** `README.md` and `README.zh-CN.md` are a pair; `references/design.md`, `writing.md`, and `production.md` are English-only sources and must not gain `*.en.md` duplicates. Chinese/English output differences belong in the templates.
- Use `OK:` / `ERROR:` for status and `Use` / `Avoid` for comparisons; no graphic emoticons in docs, template comments, or script output.
