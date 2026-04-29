<div align="center">
  <img src="https://gw.alipayobjects.com/zos/k/vl/logo.svg" width="120" />
  <h1>Folio</h1>
  <p><b>Good content deserves good paper.</b></p>
  <p><sub><a href="README.zh-CN.md">简体中文</a></sub></p>
  <p><sub>Folio is forked from <a href="https://github.com/tw93/Kami">Kami</a> and extended into a document-first design system for agent-generated deliverables.</sub></p>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square" alt="License"></a>
</div>

## What Folio Is

Folio is a document design system for the AI era: eight document types, fourteen inline SVG diagram types, and bilingual English/Chinese paths built for agent-generated deliverables.

It optimizes for stable, readable, professional output rather than novelty.

## Quick Start

**Claude Desktop**

Build or copy `dist/folio.zip`, open Customize > Skills > "+" > Create skill, and upload the ZIP directly.

**Generic agents** (Codex, OpenCode, Pi, and other tools that read from `~/.agents/`)

Use the packaged ZIP for a local install now, or publish this repository under your own namespace and install from that destination later.

Folio auto-triggers from natural requests. Tell it:

- which document type you want
- which language to use
- the raw content, notes, or draft to work from
- any current facts or source links that must be preserved
- any brand assets that matter: logo, screenshot, product image, brand color
- any output expectation that changes the default: PDF, PPTX, PNG, public draft, internal memo

Example prompts:

- `make a one-pager for my startup`
- `turn this research into a long doc`
- `write a formal letter`
- `make a portfolio of my projects`
- `build me a resume`
- `design a slide deck for my talk`
- `write an equity report on NVIDIA`
- `format these release notes`

Optional: create `~/.config/folio/brand.md` to persist identity, document defaults, and writing habits. Start from [brand.example.md](references/brand.example.md). Folio uses it as fallback context when the current request is ambiguous.

## Document Types

| Type          | Best for                                  | Example                                                              |
| ------------- | ----------------------------------------- | -------------------------------------------------------------------- |
| One-Pager     | launch brief, proposal, exec summary      | [Orbit Cache launch one-pager](assets/demos/demo-orbit-onepager.pdf) |
| Long Doc      | white paper, review, technical report     | [Agent Operations Review](assets/demos/demo-agent-ops-longdoc.pdf)   |
| Letter        | formal letter, memo, statement            | [Agent review council letter](assets/demos/demo-board-letter.pdf)    |
| Portfolio     | case studies, selected works              | [Lena Park portfolio](assets/demos/demo-ridge-portfolio.pdf)         |
| Resume        | professional resume / CV                  | [Elon Musk resume](assets/demos/demo-musk-resume.pdf)                |
| Slides        | talk deck, keynote, internal presentation | [Agent development slides deck](assets/demos/demo-agent-slides.pdf)  |
| Equity Report | investment memo, earnings brief           | [NVIDIA equity report](assets/demos/demo-nvidia-equity-report.pdf)   |
| Changelog     | release notes, version update             | [Folio release notes](assets/demos/demo-folio-changelog.pdf)         |

Templates live in `assets/templates/`. Rendered showcase assets in `assets/demos/` are kept as `PDF + PNG` only, so the table above now links every document type to a PDF example.

## Core Capabilities

### Type routing

Folio routes requests across eight document types and two language paths.

- Chinese requests route to `*.html` or `slides.py`
- English requests route to `*-en.html` or `slides-en.py`
- Slides are generated from Python, not HTML

### Content distillation

Folio can turn raw notes into structured documents instead of requiring a clean outline first.

- Meeting notes, dumps, transcripts, and scattered bullets can be distilled into template-ready sections
- Resume and portfolio content is tightened toward measurable outcomes
- Equity reports and changelogs are pushed toward evidence-first writing

### Source and material checks

Folio treats current facts and branded assets as first-class inputs.

- For current facts, it expects reliable sources before writing
- For branded documents, it checks whether logo, screenshot, product image, and brand color are available
- If critical material is missing, the gap stays explicit instead of being filled with generic visuals

### Output generation

Folio supports two main output paths:

- HTML templates -> PDF
- Python slide templates -> PPTX

Showcase demos usually keep `HTML + PDF + PNG` together so the homepage and README stay truthful.

### Cheatsheet-driven editing

Folio also carries a compact operating reference in [CHEATSHEET.md](CHEATSHEET.md).

- Use it for the shortest path to tokens, type scale, spacing, chart limits, and common CSS patterns
- Use `references/design.md` when you need the full visual system
- Use `references/writing.md` when structure is fine but content quality is weak
- Use `references/production.md` when builds, page counts, or render behavior go wrong

## Layout Rules

These are the minimum rules that matter most.

1. Page background stays parchment `#F6F0EA`, never pure white.
2. Use one accent only: cinnabar-coral `#B83D2E`.
3. One serif per page by default; do not introduce a second visual language unless the template already does.
4. Serif body stays at 400, headings at 500. Avoid synthetic bold.
5. Chinese print body usually carries light tracking; English body stays at 0.
6. Tag backgrounds must use solid hex values. Do not use `rgba()` because WeasyPrint can render a double rectangle.
7. Depth comes from ring shadow, whisper shadow, or light/dark alternation. No hard drop shadows.
8. Respect the page-count contract for each document type, especially resume and one-pager.

## Design References

Use the short guide first, then go deeper only when needed.

- [CHEATSHEET.md](CHEATSHEET.md): fast reference
- [references/design.md](references/design.md): visual system
- [references/writing.md](references/writing.md): content strategy and quality bars
- [references/production.md](references/production.md): build, verification, and troubleshooting
- [references/diagrams.md](references/diagrams.md): inline SVG diagram rules

## Travel / Image Prompting

Folio also works as a brief for image models and drawing tools. Point them at the `references/` folder and ask them to follow Folio's warm parchment palette, cinnabar-coral restraint, serif-led hierarchy, and editorial spacing.

Example illustration briefs:

- Alpine night-train travel atlas with station callouts, timetable chips, and warm editorial annotations
  ![Alpine night-train travel atlas](assets/illustrations/travel-tesla-optimus.png)

- Coastal weekend route poster with tide windows, cafe stops, and hand-marked walking segments
  ![Coastal weekend route poster](assets/illustrations/travel-spatialvla.png)

- Desert design hotel field guide with arrival map, packing cues, and restrained artifact photography framing
  ![Desert design hotel field guide](assets/illustrations/travel-3d-representations.png)

## Support

- Open an issue or PR if you find a bug, wording drift, or layout regression.
- MIT License for code and templates.
- LXGW WenKai is open-source. Charter fallbacks rely on system or open-licensed availability.
