# Diagrams

folio's drawing capability. **22 diagram types** covering structural, process, notation, and data chart scenarios. All wear folio's skin (parchment + cinnabar-coral + warm grays). No second design system.

All twenty-two official diagram types are generator-backed. Structured semantic JSON compiles through type-owned grammars into shared scene primitives and exports as SVG, PNG, or PDF. The self-contained HTML + inline SVG files and legacy UML loader remain parity references and manual escape hatches.

Artifact flow:

- `JSON spec -> SVG -> PNG -> PDF`

The generated `SVG` is the source reused by documents. Slides use a traced PNG derived from the same resolved scene.

---

## 0. Folio Technical Illustration Stroke

All diagrams should look drawn by the same editorial hand, whether they come from `assets/diagrams/*.html`, `scripts/diagram_render_svg.py`, or the homepage mini SVGs.

| Element | Canonical stroke |
|---|---|
| Arrow body | Open path / line, `stroke-linecap="round"`, no filled arrow body |
| Arrowhead | Manual two-stroke chevron path at the endpoint; never SVG `<marker>` |
| Standard node | `#FBF7F3` fill, 1px warm stroke, 6px radius for boxes |
| Focal node | `#F7E6E1` fill, `#B83D2E` stroke, 1-2 focal elements per diagram |
| Group / layer | Soft dashed outline, label in mono uppercase, behind nodes |
| Legend | Outside or below the drawing area, compact strip, no floating legend over content |
| Numbering | Mono uppercase labels for steps / layers, serif for names |
| Gridlines | Warm hairlines only; dashed reference lines stay low contrast |
| Data labels | Tabular, near-black or brand only for the focal series |

**Arrow rule**: use manual chevrons for every arrow, including axis arrows and legend samples. WeasyPrint ignores `orient="auto"` on markers, so `<marker>` and `marker-end` are banned in Folio diagram templates.

**Caption rule**: diagram captions are upright serif text. No `font-style: italic`; emphasis comes from wording and focal color alignment.

---

## 1. Selection

All twenty-two rows below are generator-backed. The `Kind` column is the registered
`kind` accepted by every `scripts/folio.py` drawing subcommand, and the `Reference payload`
column is the canonical fixture registered in `references/fixtures/diagram-catalog.json`.
Start from the fixture, do not hand-edit SVG.

| Showing… | Use | Kind | Reference payload |
|---|---|---|---|
| System components + connections | **Architecture** | `architecture` | `references/fixtures/architecture-demo.json` |
| Decision branches, "if A then B else C" | **Flowchart** | `flowchart` | `references/fixtures/flowchart/branching.json` |
| Two-axis positioning / prioritization | **Quadrant** | `quadrant` | `references/fixtures/v3/quadrant.json` |
| Category comparison (revenue, market share, quarterly) | **Bar Chart** | `bar-chart` | `references/fixtures/v3/bar-chart.json` |
| Trend over time (stock price, growth rate, time series) | **Line Chart** | `line-chart` | `references/fixtures/v3/line-chart.json` |
| Proportional breakdown (spend, user segments, share) | **Donut Chart** | `donut-chart` | `references/fixtures/v3/donut-chart.json` |
| Finite states + directed transitions (lifecycle, state machine) | **State Machine** | `state-machine` | `references/fixtures/v3/state-machine.json` |
| Time axis + milestone events (roadmap, project progress) | **Timeline** | `timeline` | `references/fixtures/v3/timeline.json` |
| Cross-responsibility process (multi-role, API request path) | **Swimlane** | `swimlane` | `references/fixtures/v3/swimlane.json` |
| Hierarchical relationships (module deps, directory tree) | **Tree** | `tree` | `references/fixtures/v3/tree.json` |
| Vertically stacked system layers (OSI, application stack) | **Layer Stack** | `layer-stack` | `references/fixtures/v3/layer-stack.json` |
| Set intersections (feature overlap, audience comparison, capability map) | **Venn** | `venn` | `references/fixtures/v3/venn.json` |
| Converging levels, funnel stages, or narrowing hierarchy | **Pyramid** | `pyramid` | `references/fixtures/v5/pyramid.json` |
| Reporting lines, unit ownership, and headcount | **Org Chart** | `org-chart` | `references/fixtures/v5/org-chart.json` |
| Self-reinforcing cycle where each stage feeds the next | **Loop Flywheel** | `loop-flywheel` | `references/fixtures/v5/loop-flywheel.json` |
| OHLC price action (stock price, trading days, up/down candles) | **Candlestick** | `candlestick` | `references/fixtures/v3/candlestick.json` |
| Revenue bridge, valuation decomposition, cash flow breakdown | **Waterfall** | `waterfall` | `references/fixtures/v3/waterfall.json` |
| Correlation between two numeric measures | **Scatter** | `scatter` | `references/fixtures/v5/scatter.json` |
| Task schedule across periods with milestones | **Gantt** | `gantt` | `references/fixtures/v5/gantt.json` |
| Ordered interactions among actors, systems, and stores | **Sequence** | `sequence` | `references/fixtures/v4/sequence.json` |
| Types, members, inheritance, association, aggregation, composition | **UML Class** | `uml-class` | `references/fixtures/v4/uml-class.json` |
| Database entities, fields, keys, and cardinality | **ER Diagram** | `er-diagram` | `references/fixtures/v4/er-diagram.json` |

Fourteen of these types also ship a hand-authored `assets/diagrams/*.html` twin. Those files are
**legacy parity references and manual escape hatches only**, never the authoring path. See section 8.

Not on the list:
- **Compare two things**: use a table. A three-column table beats any diagram of a binary contrast.
- **One box with a label**: delete the box, write the sentence.

### The question before drawing

> Would a well-written paragraph teach the reader less than this diagram?

If "no", don't draw. Diagrams add signal to hierarchy, direction, and magnitude. They don't decorate prose.

---

## 2. Complexity budget

**Target density: 4/10**. Enough to be technically complete, not so dense the reader needs a guide.

- Nodes > 9 -> this is two diagrams, not one
- Two nodes that always travel together -> they're one node
- A line whose meaning is obvious from layout -> remove the line
- 5 nodes in cinnabar-coral -> you haven't decided what's focal

**Focal rule**: 1-2 focal elements per diagram (`#B83D2E` stroke + `#F7E6E1` fill). Everything else goes neutral. Focal signal comes from contrast, not count.

---

## 3. Embedding in long-doc / portfolio

### Standalone preview

Use the structured fixtures in `references/fixtures/` and `references/fixtures/v3/`, then run `scripts/folio.py render-drawing`. Generated catalog outputs live under `assets/diagrams/generated/catalog/`.

Open `assets/diagrams/architecture.html` or another type template only for parity review or a deliberate manual escape hatch.

### Embed in a Folio document or slide

Use an explicit host slot; do not copy SVG out of a template. HTML slots use this shape:

```html
<figure data-folio-diagram-slot="system-flow">
  <p>Diagram slot</p>
</figure>
```

Then compile, embed, and verify:

```bash
python3 scripts/folio.py embed-drawing references/fixtures/v3/swimlane.json \
  --host-contract a4-portrait --host-file report.html --output-host report-filled.html \
  --slot system-flow --caption "Ownership handoffs concentrate in the compiler lane."
python3 scripts/folio.py verify-drawing-host report-filled.html
```

For slides, name the target shape `folio-diagram-slot:<id>` in the PPTX and use host contract `slide-16x9` with `--slide-index`. Folio contain-fits the image without distortion, writes alt text and a caption, records source and artifact digests in slide notes, and adds an exact data table to notes for charts. See `drawing-dsl-authoring.md` for the full workflow.

### Editing nodes / text

Direct `<text>` and `<rect>` editing is a manual escape hatch for files under `assets/diagrams/`. Rules:

The rules in this subsection apply to **hand-authored SVG templates** under `assets/diagrams/`. Generator-backed architecture diagrams use the executable grammar in `scripts/drawing/grammar/architecture.py`; see `references/drawing-dsl.md` and `references/drawing-architecture.md`. Do not copy hand-authored size tiers into the generator.

- **All coordinates, widths, and gaps must be divisible by 4.** This is the anti-AI-slop floor. Break it once and the diagram starts looking "close enough".
- Node widths: 128 / 144 / 160 (three tiers, don't add more). Small diagrams (viewBox width < 360) may compress to 2 tiers, but still keep it 2 - don't tailor each node.
- Node heights: 32 (pill) / 64 (standard)
- Font sizes: 7 (small mono label) / 9 (sublabel mono) / 12 (name sans)
- **Arrow endpoints land exactly on node edges**: start `(box.x + box.w, box.y + box.h/2)`, end `(box.x, box.y + box.h/2)`, not "close enough". A 10px gap is visible to the eye.
- **SVG top padding**: the `y` in `<text y="…">` is the baseline. `y` must be ≥ font-size × 1.2, otherwise the tops of capital letters extend above the viewBox and get clipped (classic symptom: "TOOLS" renders as "TOULS"). Either pad the viewBox at the top or move `y` into the safe zone.
- **Loop arc control points**: for a four-cardinal-node ring, each arc is a Q-curve whose control point sits at the **outer intersection of the two adjacent tangent axes**, not at a node corner. Example for PLAN (top) → ACT (right): start = PLAN's right-edge midpoint, end = ACT's top-edge midpoint, control = `(ACT.x + ACT.w/2, PLAN.y + PLAN.h/2)`. This gives a pure horizontal tangent at departure and pure vertical at arrival, reading as a clean quarter-circle. Control at the node corner produces a squashed arc.
- **Closed loops need a dashed framing ring**: four directed arcs alone force the reader to mentally connect them into a loop. A dashed circle centered on the visual center (radius slightly larger than center-to-inner-edge distance) makes the loop immediately readable. Draw the ring below the nodes; solid node fills mask where the ring crosses each node; the ring shows only between nodes.
- **Chevron arrows, not filled triangles**: use `<path d="M2 1 L8 5 L2 9" fill="none" stroke=... stroke-width="1.5" stroke-linecap="round"/>`. A filled triangle reads as technical UI; an open two-stroke chevron reads as editorial schematic. folio defaults to chevron. **WeasyPrint does not support `<marker orient="auto">`**: all markers render at 0° (pointing right). The fix is to skip `<marker>` and draw each arrowhead as a manual chevron `<path>` with hardcoded direction (see production.md #15).

### Color token map

Shared tokens across the three diagrams, mapping directly to folio's design system:

| SVG role | folio token | Value |
|---|---|---|
| Canvas | `--parchment` | `#F6F0EA` |
| Standard node fill | (white) | `#FBF7F3` |
| Standard node stroke | `--near-black` | `#191514` |
| Store node fill | near-black 5% | `rgba(25,21,20,0.05)` |
| Store node stroke | `--olive` | `#5A4A43` |
| Cloud node fill | near-black 3% | `rgba(25,21,20,0.03)` |
| Cloud node stroke | near-black 30% | `rgba(25,21,20,0.30)` |
| External node fill | olive 8% | `rgba(90,74,67,0.08)` |
| External node stroke | `--stone` | `#85776F` |
| **Focal fill** | `--brand-tint` | `#F7E6E1` |
| **Focal stroke** | `--brand` | `#B83D2E` |
| Standard arrow | `--olive` | `#5A4A43` |
| Focal arrow | `--brand` | `#B83D2E` |
| Primary text | `--near-black` | `#191514` |
| Secondary text | `--olive` | `#5A4A43` |
| Tertiary text / small mono label | `--stone` | `#85776F` |

Don't add a fourth state ("warning amber", "success green"). folio has one accent.

---

## 4. Icon style

Icons live inside `<svg>` blocks alongside diagram nodes. Draw them with the same primitives (`rect`, `circle`, `line`, `path`) used for nodes - no imported icon fonts, no SVG sprites.

**Rules**:
- Single line, stroke 1pt-1.5pt, no fill
- Stroke weight stays consistent within one diagram. Never mix 1pt and 1.5pt icons in the same figure
- No drop shadow, gradient, 3D, or glassmorphism
- No emoji-style faces, mascots, or expressive characters - this is editorial schematic, not playful
- Focal icons may use `--brand` stroke or fill, but the figure's total cinnabar-coral area still respects the 5% cap

### Canonical shapes

When an icon represents a recurring concept, use the canonical form rather than inventing a new one:

| Concept | Shape |
|---|---|
| Terminal / CLI | rounded rectangle, three dots top-left |
| Document / spec | rectangle, three short horizontal lines |
| Checklist / verification | rectangle, two check marks |
| Gear / system | 8-tooth gear outline |
| Magnifier / inspect | circle with 45° handle |
| Shield / safety | shield silhouette |
| Cloud / hosted service | three-arc cloud outline |
| Chip / hardware | square with leg lines on four sides |
| GPU / compute rack | rectangular stack with port indicators |

### Human and robot figures

Avoid human figures and anthropomorphic AI in editorial diagrams. If a person must appear, use a minimal line drawing without facial detail. Industrial robots may be line-art mechanical structures, but stop short of patent-illustration density.

When in doubt, omit the icon entirely. A clean text label beats a cute icon in editorial schematic style. Add an icon only when it carries information the label cannot (e.g. distinguishing "cloud service" from "on-device compute" at a glance).

---

## 5. AI-slop anti-patterns

Scan for these when drawing or reviewing:

| Anti-pattern | Why it fails |
|---|---|
| Dark mode + cyan / purple glow | Cheap "technical" signifier with no design decision |
| All nodes identical size | Destroys hierarchy |
| JetBrains Mono as the universal "dev" font | Mono is for technical content (ports, URLs, fields). Names go in sans. |
| Legend floating inside the diagram area | Collides with nodes |
| Arrow labels without a masking rect | Line bleeds through the text |
| Vertical `writing-mode` text on arrows | Unreadable |
| Three equal-width summary cards as a default | Template feel. Vary widths. |
| `box-shadow` on anything | folio only permits ring / whisper |
| `rounded-2xl` / border-radius above 10px | Max 6-10px. Beyond, it starts to look like App Store chrome. |
| Cinnabar Coral on every "important" node | Focal rule is 1-2, not a signaling system |
| Decorative icons | Disaster |
| Gradient backgrounds | folio forbids them |
| Focal color contradicts the caption's claim | Caption says "Simple **core**", but the ACT node is painted cinnabar-coral - two focals competing. Focal color must match the word emphasized (`<span class="hl">`) in the caption |
| Cycle diagram with a dashed ring AND four directed arcs | Same loop drawn twice; reader thinks there are two flows |
| SVG text clipped at the viewBox top | `text` y is the baseline; cap letters extend above y=0. Pad the top by font-size × 1.2 or adjust the viewBox |
| 5-10px gap between arrow endpoint and node edge | Reads as "arrow floating in space". Anchor endpoints to exact `box.x / box.x+w / box.y / box.y+h` |
| Per-node custom widths within one diagram | Four steps at widths 60 / 76 / 80 / 100 feel hand-patched. Small diagram: 2 tiers. Large: 3 tiers. That's the full budget |
| Porting an external diagram with one accent color per node type (purple/amber/green/red) | folio has one accent. When adapting external diagrams, migrate the focal to whichever element the caption's `<span class="hl">` emphasizes; concentrate color there, keep all other nodes neutral |
| Ring diagram: every node is a single word, center is empty | Four labeled boxes looping with no anchor. Either add a subtitle to each node or place one line of text at the center (exit condition, LOC count, etc.). Pick one. |

---

## 6. Common pairings

### Technical white paper
- Architecture (system overview) + built-in timeline (from long-doc)
- One architecture diagram per chapter, maximum. If you want two, the chapter is covering two topics and should split.

### Portfolio project page
- Quadrant (competitive positioning) or architecture (the layer you owned)
- **Not every project needs a diagram.** Only when the diagram says something prose can't.

### One-pager
- Quadrant (priority) or flowchart (decision path)
- One diagram only. If you're tempted to add a second, kill the weaker one.

### Resume
- **No diagrams.** Resume real-estate costs more than diagrams. Rare exception: a URL to a portfolio diagram when showing system-level capability.

### Slides
- One diagram per slide, max. The diagram is the body. Text is caption, not a sidebar.

---

## 7. Data charts (bar / line / donut)

Five data-driven chart types support investment reports, financial comparisons, and market-share breakdowns. Their structured V3 inputs own values, units, locale, source notes, category/time domains, and missing-value policy; authored coordinates are not accepted.

### Color palette (derived from folio warm palette)

| Role | Value | Use |
|---|---|---|
| Primary series | `#B83D2E` cinnabar-coral | First group / focal data |
| Series 2 | `#5A4A43` olive | Second group |
| Series 3 | `#85776F` stone | Third group |
| Series 4 | `#B9ACA3` light-stone | Fourth group |
| Series 5 | `#D7CBC2` mist | Fifth group |
| Series 6 | `#F7E6E1` brand-tint | Sixth group |
| Grid lines | `#E6D9D1` | Axes / reference lines |
| Data labels | `#191514` near-black | Numeric text |

### Data limits

| Chart | Max categories | Max series | Template |
|---|---|---|---|
| Bar chart | 8 groups | 3 series | `assets/diagrams/bar-chart.html` |
| Line chart | 12 points | 3 lines | `assets/diagrams/line-chart.html` |
| Donut chart | 6 segments | n/a | `assets/diagrams/donut-chart.html` |
| Candlestick | 30 days | n/a | `assets/diagrams/candlestick.html` |
| Waterfall | 8 segments | n/a | `assets/diagrams/waterfall.html` |

### Editing data

Edit semantic JSON rather than SVG coordinates. Use these fixture shapes as starting points:

- Bar: `categories`, `series[].values`, `mode`, optional `order`, `reference_lines`, `annotations`, `unit`, `locale`, `source`
- Line: unique `categories`, `series[].values`, `x_scale`, `missing_policy`, optional `reference_lines` and semantic `annotations`
- Donut: positive `segments`, optional `percent_total` and `tolerance`
- Candlestick: ascending ISO periods with `open`, `high`, `low`, `close`, plus optional period/field annotations
- Waterfall: `start`, signed delta contributions, verified subtotal steps, optional checked `end` and `tolerance`

For local CSV/TSV sources, use `scripts/folio.py import-chart-data` with the explicit config contract in `references/schemas/tabular-chart-import.schema.json`. Remote resources, formula-like cells, implicit separators, ambiguous dates/numbers, and unbounded files are rejected. `value_format` changes only displayed precision, grouping, compact notation, and unit placement; serialized and accessible values remain exact.

For existing Mermaid or draw.io diagrams, use `scripts/folio.py import-diagram`. It converts flowchart, sequence, state-machine, ER, and UML class sources into typed payloads and writes a fidelity ledger (`references/schemas/diagram-import-ledger.schema.json`) that lists preserved, downgraded, and dropped features. Coordinates are always dropped because Folio recomputes deterministic layout. See `references/drawing-dsl-authoring.md` section 4b.

The compiler calculates scales, ticks, baseline, positive/negative stacks, reference lines, bounded callouts, arcs, temporal spacing, candle bodies, connector levels, subtotals, and stable mark ids. Invalid numbers, totals, dates, targets, budgets, or ordering stop before export.

### Notation limits

| Diagram | Primary budget | Required identity |
|---|---|---|
| Sequence | 2-6 participants, 1-12 messages | Every participant and message has a stable id |
| UML Class | 1-8 types, 0-12 relationships | Every type and relationship has a stable id |
| ER Diagram | 2-8 entities, 1-8 fields each, 1-12 relationships | Every entity, field, and relationship has a stable id |

Sequence rejects self-messages in V4.3. UML and ER reject parallel directed relationships instead of silently collapsing routes. Authors provide no coordinates. Sankey is intentionally excluded; see `references/decisions/0007-sankey-is-not-a-v4-3-grammar.md`.

### UML Class contract

Production UML Class input uses `schema_version: "3.0"`, `kind: "uml-class"`, and optional `layout: "class-grid"`. Start from `references/fixtures/minimal/uml-class.json` or `references/fixtures/v4/uml-class.json`; the authoritative contract is `references/schemas/types/uml-class.schema.json`.

Authors provide type members and relationships, never `x`, `y`, box dimensions, connector paths, colors, or SVG. The compiler owns a bounded 960x640 grid, shared scene validation, accessibility metadata, output profiles, and SVG / PNG / PDF serialization.

| Axis | Accepted values |
|---|---|
| Type kinds | `class`, `interface`, `enum` |
| Relationship kinds | `inheritance`, `association`, `aggregation`, `composition` |
| Budget | 1-8 types, up to 6 attributes and 5 methods per type, 0-12 relationships |

Every type and relationship needs a stable id, and a relationship must reference two distinct known types. Production CLI, catalog, host, and build artifact paths use the versioned registry compiler. `scripts/diagram_models.py` is the Architecture spec contract layer that the registry compiler and the text planner both load through `load_diagram_spec`; it is not a legacy shim. Its coordinate-bearing UML branch, together with the older unversioned `references/fixtures/uml-class-demo.json` and `scripts/diagram_layout.py:layout_uml_class`, is the one remaining compatibility facade.

---

## 8. Build / preview

```bash
python3 scripts/folio.py draw-plan references/fixtures/architecture-demo.json --explain-drawing
python3 scripts/folio.py check-drawing references/fixtures/architecture-demo.json
python3 scripts/folio.py render-drawing references/fixtures/v3/bar-chart.json --format svg --profile embed --output /tmp/bar.svg
python3 scripts/folio.py render-drawing references/fixtures/v3/bar-chart.json --format png --theme dark --output /tmp/bar-dark.png
python3 scripts/folio.py diagram-catalog --skip-dsl-build
python3 scripts/build.py diagram-architecture
python3 scripts/build.py diagram-flowchart
python3 scripts/build.py diagram-quadrant
python3 scripts/build.py diagram-bar-chart
python3 scripts/build.py diagram-line-chart
python3 scripts/build.py diagram-donut-chart
python3 scripts/build.py diagram-state-machine
python3 scripts/build.py diagram-timeline
python3 scripts/build.py diagram-swimlane
python3 scripts/build.py diagram-tree
python3 scripts/build.py diagram-layer-stack
python3 scripts/build.py diagram-venn
python3 scripts/build.py diagram-candlestick
python3 scripts/build.py diagram-waterfall

# or all
python3 scripts/build.py
```

For parity review only, open `assets/diagrams/*.html` in a browser.

---

## 9. Credit

This capability is inspired by Cathryn Lavery's [diagram-design](https://github.com/cathrynlavery/diagram-design) (a Claude Code skill with 13 editorial diagram types). folio borrowed the **approach** (inline SVG, semantic tokens, complexity budget, anti-slop table). Not the full catalog.
