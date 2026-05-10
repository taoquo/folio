# Web Foundation

Folio Web is guidance for browser-page design. It is not a frontend framework, component library, or build system.

Use this file before designing any Web page with Folio's visual language. Then read `web-reading.md` for content-heavy pages or `web-workspace.md` for product UI surfaces. Finish with `web-checklist.md`.

## Design Thesis

Folio Web translates document judgment into browser behavior:

- reading pages keep argument, evidence, source, and scroll orientation visible
- workspace pages keep location, selected object, available action, and feedback visible
- hybrid pages separate reading regions from operational regions before styling either one
- motion clarifies position, state, or progressive disclosure; it is never decoration

The Web layer may use browser-native patterns such as navigation, tabs, drawers, tables, inspectors, toasts, and filters. These patterns must be expressed with Folio material: parchment base, ivory raised surfaces, one cinnabar-coral accent, warm neutrals, restrained borders, editorial type, and measured whitespace.

## Web Design Workflow

Before proposing layout, mockup, or code, define this contract:

| Step | Decision | Output |
|---|---|---|
| 1 | Page job | One sentence naming what the page helps the user understand or do. |
| 2 | Archetype | Reading / Publication, Workspace / Product UI, or Hybrid / Document Tool. |
| 3 | Primary object | The first viewport's main argument, artifact, table, queue, editor, or selected item. |
| 4 | Orientation | How the user knows location: title block, contents rail, progress, nav, selected row, or status band. |
| 5 | Required states | Loading, empty, error, disabled, selected, active, success, and failure states that matter for the task. |
| 6 | Motion thesis | Two or three motion ideas using the Motion Thesis Template below. |
| 7 | Content plan | The required content regions, evidence, actions, and feedback in page order. |
| 8 | Mobile collapse | How rails, inspectors, tables, and actions behave below 768px. |

If any row is unclear, ask or state the assumption before designing. Do not compensate for unclear page purpose with decorative cards, large type, or motion.

## Page Archetypes

| Archetype | Use | Page job | Required orientation |
|---|---|---|---|
| Reading / Publication | Articles, reports, research notes, case studies | Help readers follow a claim and inspect evidence | Title block, section path, captions, sources |
| Workspace / Product UI | Dashboards, editors, review queues, admin tools | Help users inspect state and take repeated action | Navigation, selected object, action state, feedback |
| Hybrid / Document Tool | Web pages that combine prose and operations | Keep reading and operation visually separate | Reading rail plus operational panel or inspector |

Do not start from components. Start from the page job, then choose the smallest structure that lets the user understand and act.

## Composition Rules

Every Folio Web page needs a clear first viewport:

1. State what the page is for without marketing filler.
2. Show the main object or main argument early.
3. Expose the next useful action or orientation cue.
4. Keep one focal path per viewport: one primary action, active section, selected object, or highlighted result.

Use composition before cards:

- section bands
- columns and rails
- dividers
- plain grouped rows
- tables
- figure bands
- inspectors
- sticky contents
- typographic hierarchy

Cards are allowed only when the card is a repeated object, selectable item, modal, or inspectable artifact. Page sections should not become generic floating cards.

## Page Skeletons

Use these skeletons as starting points. Adapt density and copy, but keep the orientation contract.

### Reading / Publication

```
Opening block
  title, subtitle, author/date/source
Contents rail
  sticky rail, top jump links, or progress line
Article body
  claim-led sections with readable measure
Figure band
  figures, tables, pull quotes, citations
Source notes
  source rail, notes, reference list, or citation reveal
```

### Workspace / Product UI

```
Nav
  product area, current page, active section
Toolbar
  scope, filters, freshness, primary action
Primary work area
  table, editor, preview, queue, chart, or selected artifact
Inspector
  inspector, details, checks, comments, history, metadata
Feedback
  loading, empty, error, disabled, selected, success, failure
```

### Hybrid / Document Tool

```
Reading rail
  document title, summary, source, article or preview
Document preview
  selected document, article, artifact, or generated output
Operation panel
  controls, checks, generation state, review findings
Status
  inline status tied to the selected document or paragraph
```

If a page does not fit one skeleton, name the reason and define a new skeleton before styling.

## Reading Page Structure

A reading page usually follows this sequence:

1. Opening block: title, subtitle, author, date, and source context.
2. Orientation: contents rail, progress line, or active section marker when the page is long.
3. Argument sections: each section opens with the claim before supporting detail.
4. Evidence: figures, tables, citations, and captions that state the insight.
5. Source treatment: footnotes, source rail, reference list, or citation reveal.

Reading pages should feel calm. Avoid continuous motion while body text is being read.

## Workspace Page Structure

A workspace page usually follows this structure:

1. Navigation: where the user is.
2. Toolbar or status band: current scope, filters, freshness, or primary action.
3. Primary work area: table, editor, preview, queue, chart, or selected artifact.
4. Secondary context: inspector, comments, checks, history, or metadata.
5. Feedback: loading, empty, error, disabled, selected, success, and failure states.

Workspace copy should be operational. If a sentence could sit in a landing-page hero, rewrite it as a label, status, or action.

## Shared Tokens

| Role | Token | Value | Web use |
|---|---|---|---|
| Page base | `--parchment` | `#F6F0EA` | Reading pages, warm app backgrounds |
| Raised surface | `--ivory` | `#FBF7F3` | Panels, tables, inspectors, restrained controls |
| Accent | `--brand` | `#B83D2E` | Primary action, active state, section mark |
| Primary text | `--near-black` | `#191514` | Main copy and headings |
| Secondary text | `--dark-warm` | `#3A312D` | Labels, navigation, dense UI copy |
| Supporting text | `--olive` | `#5A4A43` | Descriptions, captions, inactive items |
| Tertiary text | `--stone` | `#85776F` | Metadata, timestamps, disabled-adjacent copy |

Use `--brand` on no more than one focal path per viewport. For Web UI, this usually means one primary action, one active navigation item, or one data highlight.

## Type and Voice

Reading pages may keep the Folio serif-led voice:

```css
font-family: Charter, Georgia, Palatino, "LXGW WenKai", serif;
```

Workspace pages can remain warm and editorial without becoming decorative:

- headings may remain serif when the surface is document-like
- dense tables, numeric metrics, code, logs, and filters should use mono or compact functional text
- do not use oversized marketing headings inside operational UI
- reserve display type for true landing, publication, or cover-like openings

Minimum Web text size is 12px. Body reading text should usually sit between 16px and 19px. Dense workspace text may go to 13px or 14px only when contrast, line-height, and spacing remain readable.

## Interaction Semantics

Interactions must describe state or location.

| Interaction | Page-level meaning | Folio expression |
|---|---|---|
| Hover | This can be inspected, opened, or acted on | warm ring, slight tint, underline, or whisper lift |
| Active / click | The action was physically pressed | 1px press or brief tint inside the same shape |
| Focus-visible | Keyboard location | warm ring on the existing shape, not color alone |
| Selected | This object or section is current | left rule, tint step, active marker, or stronger label |
| Reveal | Supporting detail is now available | opacity plus 4px translate, tied to content |
| Inspector open | Secondary context is attached to the selected object | ivory panel, divider, active object reference |
| Loading | The page is waiting for real content | skeleton or progress line matching the eventual layout |
| Empty | There is no content yet | explain how to populate or start |
| Error | Something failed and can be recovered | inline, specific, and action-oriented |

Browser-native UI patterns are allowed. They are wrong only when they introduce a separate visual language.

## Motion Layers

Think in layers before naming animation details:

| Layer | Purpose | Examples | Limits |
|---|---|---|---|
| Page motion | Establish orientation over time | first-section reveal, reading progress, active section marker | Never move body text while it is being read. |
| Region motion | Attach or remove context | inspector open, drawer reveal, sticky rail change | Preserve the user's sense of where the selected object lives. |
| Object motion | Show selection or expansion | selected row, active figure, source note highlight | Do not shift neighboring content unpredictably. |
| Control motion | Confirm affordance or action | hover, active press, focus-visible ring | Keep distance inside the 4pt rhythm. |

## Motion Thesis Template

Use this template before choosing animation details. Keep only the layers that serve the page job; prefer two or three meaningful motions per page.

```text
Motion thesis:
- Page motion: This motion means the user is oriented within the page by ...
- Region motion: This motion means secondary context is attached to or removed from ...
- Object motion: This motion means the current object, row, figure, source, or section is ...
- Control motion: This motion means the control can be acted on, is being pressed, or has completed ...
```

Rules:

- At least one motion should normally be page, region, or object level.
- Control motion cannot replace page, region, or object motion unless the page is only a simple form or static notice.
- Hover only means affordance; it cannot carry page narrative or selection state by itself.
- If a layer is omitted, write `Not used because ...` instead of inventing animation.
- If a proposed motion cannot be written as `This motion means ...`, remove it.

Default durations:

| Motion | Duration | Distance |
|---|---:|---:|
| Active press | 80-120 ms | 1px |
| Hover feedback | 150-200 ms | 0-2px |
| Object selection | 120-180 ms | 0-4px |
| Region reveal | 180-280 ms | 4-8px |
| Page reveal | 220-360 ms | 8-16px |

## Motion Boundaries

Motion should make hierarchy, position, or state easier to understand.

Use:

- section reveal
- sticky context changes
- reading progress
- active section marker
- figure/caption reveal
- hover and active feedback
- inspector open/close
- selected-row transition
- inline status changes

Avoid:

- cinematic scroll hijacking
- large parallax as decoration
- neon glow
- particles
- perpetual motion in reading surfaces
- moving tables or controls while the user is targeting them
- animation that hides content or delays task completion

Animate `transform` and `opacity` by default. Do not animate layout dimensions unless the implementation stack handles it safely. Always include a reduced-motion path.

## Folio Web Translation Rules

Folio Web is not "make everything look like a PDF."

## When Not To Use Document Feeling

Use more document character when:

- the page is content-heavy
- the user is reading, citing, comparing, or sharing
- the first viewport behaves like an opening title block
- figures, captions, and source treatment carry the experience

Use more functional UI when:

- the user repeats actions
- tables, filters, logs, queues, or editors dominate
- scanning labels and numbers matters more than prose
- selection, feedback, and recovery states drive the task

Keep Folio identity through material and restraint: parchment warmth, ivory surfaces, single cinnabar accent, warm neutrals, careful borders, and editorial spacing. Do not force serif hierarchy, large whitespace, or cover-like composition into dense operational UI.

## Agent Output Contract

When asked to guide or implement a Web page, provide or internally satisfy this structure before finalizing:

```text
Visual thesis: mood, material, and energy in one sentence.
Page job: what the page helps the user understand or do.
Archetype: Reading / Workspace / Hybrid.
Content plan: required content regions, evidence, actions, and feedback in page order.
Primary object: what must be visible in the first viewport.
Page skeleton: named regions in top-to-bottom or left-to-right order.
Interaction thesis: 2-3 motions using the Motion Thesis Template; include at least one page, region, or object motion unless the page is only a simple form or static notice.
State coverage: loading, empty, error, disabled, selected, success as applicable.
Mobile collapse: how rails, inspectors, tables, and actions collapse.
Final quality gate: why the design is not a generic card grid or decorative animation.
```

For implementation code, this contract can be summarized in comments, PR notes, or the response. For design guidance, show it directly.

## Responsive Rules

- Mobile should collapse to one primary column.
- Sticky rails become top jump links or collapsible contents.
- Inspectors become drawers or inline detail sections.
- Tables need a readable narrow-screen strategy before they are accepted.
- Tap targets should be at least 40px in the primary interaction path.
- First viewport content must fit on common mobile and desktop sizes without hiding the primary page job.

## Accessibility

- Keep visible focus states.
- Maintain strong contrast on parchment and dark surfaces.
- Do not rely on hover-only controls.
- Do not convey state by cinnabar color alone.
- Respect reduced-motion preferences when code is generated.
- Do not hide critical actions behind hover on mobile.

## Quality Gates

Reject or revise the design when any answer is "no":

- Does the first viewport explain the page job?
- Is there one visible primary object or argument?
- Would the page still work if all cards were removed or replaced by sections, rails, rows, and dividers?
- Can the page be understood by scanning headings, labels, and numbers?
- Does every card represent a real object, item, modal, or inspectable artifact?
- Can every motion be written as `This motion means ...` and explain position, state, or progressive disclosure?
- Does the motion thesis include a non-control layer unless the page is only a simple form or static notice?
- Does mobile use taps, drawers, or inline detail instead of hover-only behavior?
- Is there only one focal path per viewport?
- Can the design keep its identity if decorative shadows are removed?

## Forbidden Patterns

- generic three-card SaaS feature rows as a default
- pure white page base for Folio-branded pages
- cool gray UI palettes
- multiple bright accent colors
- decorative gradient backgrounds
- marketing copy inside product workspaces
- dashboard mosaics where every metric sits in an identical card
- control-only motion systems where hover, active, or focus are treated as the whole motion language
- motion that exists only to make the page feel dynamic
- Web-only components that ignore Folio material, type, spacing, or accent rules
