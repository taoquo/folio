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

- English: `make a one-pager for my startup` / `turn this research into a long doc` / `write a formal letter` / `make a portfolio of my projects` / `build me a resume` / `design a slide deck for my talk` / `write an equity report on Tesla` / `format these release notes`
- 中文: `帮我做一份一页纸` / `帮我排版一份长文档` / `帮我写一封正式信件` / `帮我做一份作品集` / `帮我做一份简历` / `帮我做一套演讲幻灯片` / `帮我写一份个股研报` / `帮我整理更新日志`

Optional: create `~/.config/folio/brand.md` to persist identity, document defaults, and writing habits. Start from [brand.example.md](references/brand.example.md). Folio uses it as fallback context when the current request is ambiguous.

## Document Types

| Type | Best for | Demo |
|---|---|---|
| One-Pager | launch brief, proposal, exec summary | [demo-orbit-onepager.pdf](assets/demos/demo-orbit-onepager.pdf) |
| Long Doc | white paper, review, technical report | [demo-agent-ops-longdoc.pdf](assets/demos/demo-agent-ops-longdoc.pdf) |
| Letter | formal letter, memo, statement | [demo-board-letter.pdf](assets/demos/demo-board-letter.pdf) |
| Portfolio | case studies, selected works | [demo-ridge-portfolio.pdf](assets/demos/demo-ridge-portfolio.pdf) |
| Resume | professional resume / CV | [demo-musk-resume.pdf](assets/demos/demo-musk-resume.pdf) |
| Slides | talk deck, keynote, internal presentation | [demo-agent-slides.pdf](assets/demos/demo-agent-slides.pdf) |
| Equity Report | investment memo, earnings brief | [demo-tesla.pdf](assets/demos/demo-tesla.pdf) |
| Changelog | release notes, version update | [demo-folio-changelog.pdf](assets/demos/demo-folio-changelog.pdf) |

Templates live in `assets/templates/`. Every type above has a real demo asset in `assets/demos/`: clickable PDF, matching HTML source, and PNG preview.

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

Examples live in `assets/illustrations/`:

- Tesla Optimus patent overview
- SpatialVLA architecture redraw
- 3D representation tradeoff chart

## Support

- Open an issue or PR if you find a bug, wording drift, or layout regression.
- MIT License for code and templates.
- LXGW WenKai is open-source. Charter and CJK fallbacks rely on system or open-licensed availability.
