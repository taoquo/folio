<div align="center">
  <img src="assets/images/folio-mark.svg" width="120" />
  <h1>Folio</h1>
  <p><b>For documents worth keeping.</b></p>
  <p><sub>Folio is forked from <a href="https://github.com/tw93/Kami">Kami</a> and extended into a document-first design system for agent-generated deliverables.</sub></p>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square" alt="License"></a>
</div>

<p align="center">
  <a href="index-en.html">
    <img src="assets/demos/readme-overview-en.png" alt="Folio document overview" width="100%">
  </a>
</p>

<p align="center">
  <a href="index-en.html"><b>Visual Gallery</b></a> ·
  <a href="assets/demos/"><b>All Demos</b></a> ·
  <a href="README.zh-CN.md"><b>中文说明</b></a>
</p>

## See Folio First

Folio is a document design system for the AI era: eight document types, fourteen inline SVG diagram types, two standalone diagram artifact kinds, bilingual English/Chinese paths, and Web guidance for reading pages and product workspaces built for agent-generated deliverables.

It optimizes for stable, readable, professional output rather than novelty.

Folio does not treat documents as neutral output. It treats them as the form through which thought becomes public, readable, and durable. Warm parchment slows the page down, serif gives judgment a voice, cinnabar marks what matters, and whitespace protects the reader's attention.

Read the full project text in [references/manifesto.md](references/manifesto.md). Chinese edition: [MANIFESTO.zh-CN.md](MANIFESTO.zh-CN.md).

What matters on first contact:

- eight document types, each with a stable editorial layout
- standalone architecture and UML class diagram artifacts with `SVG + PNG + PDF` output
- bilingual English and Chinese generation paths
- Web guidance for reading pages and product workspaces without turning Folio into a frontend framework
- PDF- and PPTX-oriented outputs instead of generic HTML mockups
- visual consistency across one-pagers, reports, decks, resumes, and release notes

## Document Gallery

<table>
  <tr>
    <td width="50%" valign="top">
      <a href="assets/demos/demo-orbit-onepager.pdf"><img src="assets/demos/demo-orbit-onepager.png" alt="Orbit Cache one-pager preview"></a><br>
      <b>One-Pager</b><br>
      Launch brief, proposal, exec summary.
    </td>
    <td width="50%" valign="top">
      <a href="assets/demos/demo-agent-ops-longdoc.pdf"><img src="assets/demos/demo-agent-ops-longdoc.png" alt="Agent operations long doc preview"></a><br>
      <b>Long Doc</b><br>
      White paper, review, technical report.
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <a href="assets/demos/demo-board-letter.pdf"><img src="assets/demos/demo-board-letter.png" alt="Board letter preview"></a><br>
      <b>Letter</b><br>
      Formal letter, memo, statement.
    </td>
    <td width="50%" valign="top">
      <a href="assets/demos/demo-ridge-portfolio.pdf"><img src="assets/demos/demo-ridge-portfolio.png" alt="Portfolio preview"></a><br>
      <b>Portfolio</b><br>
      Case studies, selected works.
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <a href="assets/demos/demo-musk-resume.pdf"><img src="assets/demos/demo-musk-resume.png" alt="Resume preview"></a><br>
      <b>Resume</b><br>
      Professional resume and CV.
    </td>
    <td width="50%" valign="top">
      <a href="assets/demos/demo-agent-slides.pdf"><img src="assets/demos/demo-agent-slides.png" alt="Slides preview"></a><br>
      <b>Slides</b><br>
      Talk deck, keynote, internal presentation.
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <a href="assets/demos/demo-nvidia-equity-report.pdf"><img src="assets/demos/demo-nvidia-equity-report.png" alt="Equity report preview"></a><br>
      <b>Equity Report</b><br>
      Investment memo, earnings brief.
    </td>
    <td width="50%" valign="top">
      <a href="assets/demos/demo-folio-changelog.pdf"><img src="assets/demos/demo-folio-changelog.png" alt="Changelog preview"></a><br>
      <b>Changelog</b><br>
      Release notes, version update.
    </td>
  </tr>
</table>

## Diagram Artifact Gallery

<table>
  <tr>
    <td width="33.33%" valign="top">
      <a href="assets/demos/demo-architecture.pdf"><img src="assets/demos/demo-architecture.png" alt="Architecture diagram artifact preview"></a><br>
      <b>Agent Runtime</b><br>
      Request-driven runtime case: gateway ingress, planning, model execution, tool use, retrieval memory, and observability.
    </td>
    <td width="33.33%" valign="top">
      <a href="assets/demos/demo-workflow-engine.pdf"><img src="assets/demos/demo-workflow-engine.png" alt="Workflow engine diagram artifact preview"></a><br>
      <b>Workflow Engine</b><br>
      Workflow orchestration case: ingress, orchestration, worker execution, state persistence, and event-based continuation.
    </td>
    <td width="33.33%" valign="top">
      <a href="assets/demos/demo-data-platform.pdf"><img src="assets/demos/demo-data-platform.png" alt="Data platform artifact preview"></a><br>
      <b>Data Platform</b><br>
      Policy-driven layout case: pipeline spine, warehouse serving, and supporting read paths rendered from one reusable grammar.
    </td>
  </tr>
  <tr>
    <td width="33.33%" valign="top">
      <a href="assets/demos/demo-uml-class.pdf"><img src="assets/demos/demo-uml-class.png" alt="UML class artifact preview"></a><br>
      <b>Agent Session Model</b><br>
      UML domain model with interfaces, enum lifecycle state, composition, aggregation, and retrieval-memory associations.
    </td>
  </tr>
</table>

## From Prompt To Output

1. Start with raw notes, a draft, source links, or a loose request like `make a one-pager for my startup`.
2. Folio routes the request to the right document type and language path, then reshapes the content into a template-ready structure.
3. The output lands as a stable PDF or PPTX with Folio's parchment canvas, serif hierarchy, and restrained cinnabar-coral accent.
4. For standalone architecture or UML class requests, the output can also land as a reusable `SVG + PNG + PDF` diagram artifact.

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
- `generate a system architecture diagram`
- `draw a UML class diagram for this module`
- `guide a web reading page for this report`
- `design a Folio-style product workspace`

Optional: create `~/.config/folio/brand.md` to persist identity, document defaults, and writing habits. Start from [brand.example.md](references/brand.example.md). Folio uses it as fallback context when the current request is ambiguous.

Templates live in `assets/templates/`. Rendered showcase assets in `assets/demos/` are kept as `PDF + PNG`, so README can stay visual without trying to recreate the full homepage inside Markdown.

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

### Web guidance

Folio can guide browser-page design while keeping its static document build pipeline unchanged.

Every Web request starts with a design contract before layout, mockup, or code:

| Step | Required decision | Visible result |
|---|---|---|
| 1 | Page job, archetype, primary object, and orientation | The first viewport explains what the page is for |
| 2 | Content plan and page skeleton | Reading, workspace, or hybrid regions are named before components |
| 3 | Required states and motion thesis | Loading, empty, error, selected, and success states have semantic motion |
| 4 | Mobile collapse plan and final quality gate | Narrow screens do not depend on hover or hidden desktop-only controls |

Page skeletons replace component galleries:

- Reading: opening block / contents rail / article body / figure band / source notes
- Workspace: nav / toolbar / primary work area / inspector / feedback
- Hybrid: reading rail / document preview / operation panel / status
- Web guidance is a design reference for agents; it does not add a Web app build chain or change Folio's PDF / PPTX / SVG outputs

Motion thesis must explain meaning, not decoration:

| Layer | Template |
|---|---|
| Page motion | `This motion means the user is oriented within the page by ...` |
| Region motion | `This motion means secondary context is attached to or removed from ...` |
| Object motion | `This motion means the current object, row, figure, source, or section is ...` |
| Control motion | `This motion means the control can be acted on, is being pressed, or has completed ...` |

Use only the layers that serve the page job. Hover, active, and focus cannot become the whole motion system.

### Output generation

Folio supports two main output paths:

- HTML templates -> PDF
- Python slide templates -> PPTX
- Diagram specs -> SVG + PNG + PDF

Showcase demos usually keep `HTML + PDF + PNG` together so the homepage and README stay truthful.

### Cheatsheet-driven editing

Folio also carries a compact operating reference in [CHEATSHEET.md](CHEATSHEET.md).

- Use it for the shortest path to tokens, type scale, spacing, chart limits, and common CSS patterns
- Use `references/design.md` when you need the full visual system
- Use `references/writing.md` when structure is fine but content quality is weak
- Use `references/production.md` when builds, page counts, or render behavior go wrong
- Use `references/web-foundation.md`, `references/web-reading.md`, `references/web-workspace.md`, and `references/web-checklist.md` when guiding browser-page design

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
- [references/web-foundation.md](references/web-foundation.md): Web guidance foundation for reading pages and product workspaces

## Travel / Image Prompting

Folio also works as a brief for image models and drawing tools. Point them at the `references/` folder and ask them to follow Folio's warm parchment palette, cinnabar-coral restraint, serif-led hierarchy, and editorial spacing.

Example illustration briefs:

<table>
  <tr>
    <td width="33.33%" valign="top" align="center">
      <img src="assets/illustrations/travel-tesla-optimus.png" alt="Alpine night-train travel atlas"><br>
      Alpine night-train travel atlas with station callouts, timetable chips, and warm editorial annotations
    </td>
    <td width="33.33%" valign="top" align="center">
      <img src="assets/illustrations/travel-spatialvla.png" alt="Coastal weekend route poster"><br>
      Coastal weekend route poster with tide windows, cafe stops, and hand-marked walking segments
    </td>
    <td width="33.33%" valign="top" align="center">
      <img src="assets/illustrations/travel-3d-representations.png" alt="Desert design hotel field guide"><br>
      Desert design hotel field guide with arrival map, packing cues, and restrained artifact photography framing
    </td>
  </tr>
</table>

## Support

- Open an issue or PR if you find a bug, wording drift, or layout regression.
- MIT License for code and templates.
- LXGW WenKai is open-source. Charter fallbacks rely on system or open-licensed availability.
