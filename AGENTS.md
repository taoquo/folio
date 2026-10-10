# Folio

Folio is a document design system with warm parchment canvas, cinnabar-coral accent, serif-led hierarchy, and editorial whitespace across eight document templates and twenty-three generator-backed diagram types.

## Structure

| Path | Purpose | Change frequency |
|---|---|---|
| `SKILL.md` | Codex routing and operating rules | Low |
| `CHEATSHEET.md` | Quick design reference, English-only source | Low |
| `references/design.md` | Design system spec, English-only source | Low |
| `references/writing.md` | Content strategy + quality bars per document type, English-only source | Low |
| `references/production.md` | WeasyPrint build and troubleshooting runbook, English-only source | Medium |
| `references/drawing-dsl.md` | Drawing DSL scope, compiler stages, routing, and output layer | Low |
| `references/drawing-dsl-v6-final-audit.md` | Closing program audit, gate evidence, and known limits | Low |
| `assets/templates/` | 8 document templates in 2 base language families | Medium |
| `assets/demos/` | README showcase demos, regenerate after visual changes | Medium |
| `assets/diagrams/generated/catalog/` | 23 generated catalog artifacts per format, SVG / PNG / PDF | Medium |
| `scripts/build.py` | PDF / PPTX build and verification script, plus placeholder / orphan / rhythm checks | Low |
| `scripts/folio.py` | Drawing DSL CLI, routing, render, import, catalog | Low |
| `scripts/page_contracts.py` | Single source for page-count contracts, consumed by every checker | Low |
| `scripts/document_ir/` | Document IR: model, validator, readers, HTML and PPTX writers | Medium |
| `scripts/renderers/` | Renderer protocol and the WeasyPrint adapter | Low |
| `scripts/pipeline.py` | Chooses the render path via `FOLIO_PIPELINE` | Low |
| `scripts/fidelity.py` | Measures the IR path against the template path, per document type | Medium |
| `scripts/projection.py` | Projects the resolved style and layout policy into a document's stylesheet | Medium |
| `scripts/document_build.py` | Builds a finished document from content, choosing the path by configuration | Medium |
| `scripts/spacing_probe.py` | Reads a rendered document's spacing back and compares it with the model | Low |
| `scripts/package-skill.sh` | Codex Desktop ZIP packager, excluding large fonts | Low |
| `CHANGELOG.md` | Aggregated release highlights linking to full notes | Medium |
| `docs/releases/` | Archived release notes for superseded versions | Low |
| `pyproject.toml` | Interpreter floor and ruff lint configuration shared with CI | Low |
| `dist/folio.zip` | Codex Desktop ZIP build output, rebuilt on demand, not tracked in git | Medium |

Reference docs are English-only. Do not recreate `*.en.md` duplicates. Chinese / English output differences belong in the templates.
Do not use graphic emoticons in docs, template comments, or script output. Use `OK:` / `ERROR:` for status and `Use` / `Avoid` for comparisons.

## Verification

```bash
python3 scripts/build.py          # build all example PDFs, diagram PDFs, and slide PPTX
python3 scripts/build.py --check  # scan templates for CSS rule violations
python3 scripts/build.py --sync   # check CSS token drift across templates
python3 scripts/build.py --check-index  # check homepage miniature parity across index.html / index-zh.html
python3 scripts/build.py --verify # verify templates, page counts, fonts, and slides
python3 scripts/build.py --check-placeholders     # scan every published HTML artifact, as CI does
python3 scripts/build.py --check-placeholders path/to/filled.html
python3 scripts/build.py --check-orphans [path/to/doc.pdf]  # scan for orphan trailing lines in built PDFs
python3 scripts/build.py --check-rhythm  # warn on monotonous slide sequences, as CI does
```

Document engine checks. These gate the IR path and the measured quality of every document:

```bash
python3 scripts/corpus.py validate            # every fixture is well formed
python3 scripts/corpus.py coverage            # composition and adversarial share
python3 scripts/profile_check.py              # 36 profiles, shape and meaning
python3 scripts/document_baseline.py compare  # documents match the approved baseline
python3 scripts/pipeline.py rollback-drill    # every mode can be left by configuration
python3 scripts/migration.py status           # IR readiness per document type
python3 scripts/fidelity.py measure           # IR path against the template path
python3 scripts/projection.py check           # the style projection layer is well formed
python3 scripts/spacing_probe.py compare --genre one-pager   # rendered spacing vs the model
```

Lint runs from the shared `pyproject.toml` config, so local and CI results match:

```bash
ruff check .                      # same rule set the fast-gate CI job enforces
```

Expected page counts: one-pager 1 / letter 1 / resume 2 strict / long-doc 7 +/- 2 / portfolio 6 +/- 2 / slides 7 +/- 3 / equity-report 2-3 / changelog 1-2

Page contracts live in `scripts/page_contracts.py` and are consumed by both `build.py` (hard gate) and `stabilize.py` (overflow solver). Change them there, never in a consumer.

**PDF metadata**: `build.py` automatically sets `/Author` from `git config user.name` (or `FOLIO_AUTHOR` env var) when the HTML template contains a placeholder like `{{作者}}` or `{{AUTHOR}}`. `/Producer` and `/Creator` are always set to `"Folio"`.

## The IR path

Documents are produced through a semantic model, and the HTML template is one renderer of it.

```bash
FOLIO_PIPELINE=ir          # the default: the document is built from the IR
FOLIO_PIPELINE=ir-shadow   # the template output is delivered; the IR runs alongside
FOLIO_PIPELINE=legacy      # the template path alone, kept for rollback
```

The compatibility writer fills the template's own markup rather than rebuilding it, because a template's appearance is its DOM shape and not its class names. Two consequences follow, and both matter:

- **A template edit needs the mapping re-checked.** Run `python3 scripts/fidelity.py measure`. All seven document types render at SSIM 1.0000 against the template path; a drop means the writer and the template have drifted apart.
- **A structural label belongs in a placeholder.** If a template hard-codes wording that the IR should carry — a section heading, a stage label — promote it to a placeholder and give it a default in `scripts/section_defaults.py`, so the template still renders on its own.

IR documents declare no font size, colour, margin or coordinate. A test walks every model field against a banned-vocabulary list, so a theme is referenced by name and never inlined. `references/schemas/document-1.0.schema.json` is the shape; `scripts/document_ir/validate.py` is the gate.

### Where a style reaches the page

`scripts/projection.py` appends the resolved style and the layout policy inside a template's own `<style>` element. The template is not edited, so the change is reversible by configuration and reviewable as a diff of the injected block alone.

| Switch | Default | Effect |
|---|---|---|
| `FOLIO_STYLE_PROJECTION` | on | projects the resolved style as CSS variables |
| `FOLIO_LAYOUT_POLICY` | off | projects keep and break rules |
| `FOLIO_BUILD_MANIFEST` | on | writes a build manifest beside the artifact |

Turning the style projection off restores the previous rendering exactly. That was measured rather than assumed: seven document types build to the same page count and SSIM 1.00000 with it on and off, because the values projected are the ones the templates already use.

Do not replace a template's spacing with the model's rules. A differential experiment found that changing one `margin-top` to `padding-top` moved the rendering to SSIM 0.90 — the two are not the same thing. `spacing_probe.py` reads spacing back and compares it, which is the safe direction.

PPTX is produced by `scripts/document_ir/writers/pptx.py`. Slides have no template path, so `fidelity.py` does not measure them.

## Documentation language

Chinese and English documentation must stay in step. `README.md` and `README.zh-CN.md` are a pair, and so are `MANIFESTO.zh-CN.md` and `references/manifesto.md`. A change to one is a change to both; do not leave a translated pair describing different products. `references/design.md`, `references/writing.md` and `references/production.md` are English-only sources and have no Chinese duplicate by design.

## Demo Screenshots

Current demos in `assets/demos/`:

| Demo | Source | Type |
|---|---|---|
| `demo-tesla.*` | Tesla Q1 2026 equity report (CN) | equity-report |
| `demo-musk-resume.*` | Elon Musk resume (EN) | resume |
| `demo-agent-slides.*` | Agent development slides (EN) | slides |
| `demo-architecture.*` / `demo-workflow-engine.*` / `demo-data-platform.*` | Architecture artifacts | diagram artifact |
| `demo-uml-class.*` / `demo-flowchart-v2.*` | Notation and flow artifacts | diagram artifact |
| `drawing-dsl-all-types.png` / `drawing-dsl-supported-types.png` | Rendered 23-type contact sheets | diagram catalog |

Diagram demos and contact sheets are generated, never hand-assembled. Rebuild them with `python3 scripts/build.py <artifact-target>` and `python3 scripts/folio.py diagram-catalog`, then re-check the approved visual baseline with `python3 scripts/folio.py diagram-catalog --baseline references/fixtures/drawing/catalog-baseline-v3.json`.

All demo PNG files use **1241x1754px** (first A4 portrait page at 150dpi).

For one-page and multi-page documents (one-pager / letter / resume / portfolio / long-doc / equity-report), capture page 1:
```bash
pdftoppm -r 150 -f 1 -l 1 -png <pdf> /tmp/p && cp /tmp/p-1.png <target>.png
```

For landscape slides, capture the first 2 pages, resize each to 867px high, add a 20px gap, then extend to 1241px wide:
```bash
pdftoppm -r 150 -f 1 -l 2 -png <pdf> /tmp/sl
magick /tmp/sl-1.png -resize x867 /tmp/sl1.png
magick /tmp/sl-2.png -resize x867 /tmp/sl2.png
magick -size $(identify -format '%w' /tmp/sl1.png)x20 xc:'#F6F0EA' /tmp/gap.png
magick /tmp/sl1.png /tmp/gap.png /tmp/sl2.png -append /tmp/stacked.png
magick /tmp/stacked.png -gravity Center -background '#F6F0EA' -extent 1241x1754 <target>.png
```

## Change Rules

- Style changes: update `references/design.md` and the matching template `<style>` tokens, then run `build.py` and confirm page counts stay stable.
- Content changes: keep CSS unchanged, edit only the body, then run `build.py`.
- New templates: copy the nearest existing template, keep it aligned with `design.md`, add routing to `SKILL.md`, and add demos.

## High-Risk Pitfalls

See `references/production.md` Part 4.

1. Tag rgba double rectangle: use solid hex backgrounds.
2. Thin border plus border radius double ring: border < 1pt with border-radius can trigger it.
3. Resume 2-page overflow: tiny font, fallback, line-height, or margin changes can break it.
4. `break-inside` fails inside flex: wrap content in a block wrapper.
5. `height: 100vh` is unreliable under `@page`: use explicit mm values.
6. SVG marker `orient="auto"` does not rotate in WeasyPrint: draw arrowheads manually.
7. Section body text should not use `max-width`: `.manifesto`, `.section-lede`, and similar text should fill the `.page` container. Exceptions: `.type-sample` and `.footer .colophon`.
8. Diagram template changes must sync to index showcase SVGs: any visual fix to `assets/diagrams/*.html` must also be applied to the matching mini SVG in `index.html` and `index-zh.html`. `python3 scripts/build.py --check-index` gates this: miniature geometry must match byte for byte, only `<text>` copy may differ.

## Release Flow

Run this before publishing or refreshing the latest package artifact:

```bash
bash scripts/package-skill.sh        # writes dist/folio.zip (<5MB, excludes LXGW WenKai TTF)
python3 scripts/build.py --verify
```

`dist/folio.zip` is a build output ignored by git, so rebuild it on every release instead of committing it. If you publish the project to a repository host, upload the freshly built ZIP to your project-owned release destination and keep all download links aligned with that destination.

Release notes must follow this project format:

1. Centered logo, release title, and one-line tagline.
2. `### Changelog` with an English numbered list.
3. `### 更新日志` with the matching Chinese numbered list.
4. Optional special-thanks paragraph when contributors need credit.
5. Final blockquote with one concise project description sentence and the repository URL.

Do not mix English and Chinese inside the same numbered item. Keep both lists aligned by number, use 5-8 items, and write one concise sentence per item. Do not use graphic emoticons in the release title or body unless the user explicitly asks for them.

Keep the current release note as `RELEASE_NOTES_V<version>.md` at the repository root, move the superseded one into `docs/releases/`, and add a matching section at the top of `CHANGELOG.md`. `scripts/package-skill.sh` bundles both locations.

## Fonts

`LXGWWenKai-Regular.ttf` is an open-source font from the LXGW WenKai project.
Fallback without LXGW WenKai: Source Han Serif SC -> Noto Serif CJK SC -> Songti SC -> STSong -> Georgia.
English templates use Charter serif.
The Codex Desktop ZIP does not bundle LXGW WenKai TTF files. They are about 24MB each and can make upload or execution time out. Before building Chinese documents, the skill checks for missing fonts and downloads them from the official GitHub source into `assets/fonts/`. WeasyPrint then uses the existing relative `@font-face` paths without changing HTML.
