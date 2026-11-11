# Web density and colour

## 1. Density

Every number below is an engine value, resolved from
`references/profiles/web/folio-v1.yaml` and injected as a custom property. The
Web layer does not invent a type scale, and `base.css` reads no literal.

| Element | Engine role | Screen value | Band |
|---|---|---|---|
| Body | `type.body` | 16px | 15–20px |
| Long reading | `type.reading` | 17px | — |
| Lead | `type.lead` | 20px | — |
| Dense / table | `type.dense` | 13px | — |
| H1 | `type.h1` | 48px | — |
| H2 | `type.h2` | 30px | 26–34px |
| H3 | `type.h3` | 20px | — |
| Caption / label | `type.caption`, `type.label` | 12 / 11px | — |
| Page padding | spacing `xl` | 32px | 24–40px |
| Card padding | spacing `lg` | 18px | 14–24px |
| Table row | `layout.table_row` | 32px | 28–40px |
| Figure height | host slot 660px / 760px wide | 275–550 / 315–635px | rendered |

The screen scale is the Web profile's own ladder, not a point-for-pixel
translation of the print profile: a reading page is read at arm's length, and
the type is sized for that. Line height stays inside the engine's bands —
headings 1.10–1.35, dense 1.50, reading 1.60–1.62.

Rules: **W-DEN-01** body, **W-DEN-02** H2, **W-DEN-03** page padding,
**W-DEN-04** card padding, **W-DEN-05** table row, **W-DEN-06** measure,
**W-DEN-07** no arrow flows inside table cells, **W-DEN-08** no template-decided
type or spacing, **W-DEN-09** the Web profile variables are present.

The figure band follows the DSL canvas bands at the page's own slot: a 400–800
unit stage renders 275–550px at 660px, and 315–635px at the wide step's 760px.
The band is derived, not chosen — widen the slot and the band moves with it.

## 2. Measure (C3)

A paragraph column is **60–95 characters** wide. The reading page is a single
column: the text, the figures, the tables and their captions share one width
(the page's content box), so the page has one right edge. The base sheet sets
`measure.body` to `76ch` inside a 660px column; a window of 1280px or more takes
one step to `93ch` inside 760px, and the figures widen with it. The measure never
binds inside its own column at either step. Wider than 95 and the eye loses the
return line; narrower and the page turns into a column of cards. Rule:
**W-DEN-06**, read from the resolved `max-width`.

## 3. Colour: three layers, all engine-owned

| Layer | Role family | Where it appears |
|---|---|---|
| L1 interface | `color.accent.*`, `color.text.*`, `color.surface.*`, `color.border.*` | shell, headings, links, table headers |
| L2 content semantics | `color.semantic.*` (20 roles) | tags, card rules, stage marks, figure fills |
| L3 figures | the drawing DSL, coloured by the document scheme (`folio_theme_for`) | the page never colours a figure |

The ten L2 meanings are **roles, not colours**. Each scheme binds every role to
its own palette, so the same meaning keeps the same role while the colour follows
the theme — a forest page states “passed” in forest pigment, not in a colour
borrowed from another design system:

`delivered` · `info` · `component` · `passed` · `attention` · `enhance` ·
`risk` · `change` · `input` · `pending`, each with a `-strong` text variant.

No scheme may introduce a hue the engine palette does not already own.

### Rules

| Rule | Statement | Check |
|---|---|---|
| W-COL-01 | No hex outside the injected `:root`. Components read variables only. | `W-COL-01` |
| W-COL-02 | The page carries the engine theme variables (surface, text, accent, semantic). | `W-COL-02` |
| W-COL-03 | Do not rewrite `--color-accent-brand` in a component rule. | review |
| W-COL-04 | Interface skeleton never uses an L2 semantic colour for structure. An `insight` may use the accent rule only. | review |
| W-COL-05 | A figure uses at most four colour variables. | `W-GEO-01` |
| W-COL-06 | Every custom property the page reads is defined. | `W-COL-06` |
| W-COL-07 | Every semantic mark names one of the ten meanings. | `W-COL-07` |

Forbidden: a per-module theme colour, a second accent, rainbow numbering,
semantic colours in the page chrome, and any code-block syntax palette that is
not the engine's.

## 4. Code block

The engine's own block: `--color-surface-card` surface, 0.5pt border, 6pt radius, mono at
9pt / 1.5 line height. On screen that is 12px / 1.5. No syntax theme from
another design system, no language-coloured background.

A quoted formula is the same mono voice with the source marker instead of a
full frame: `p.formula` keeps one expression per line, sits in the figure slot
rather than the reading measure, and scrolls instead of wrapping when the
expression is longer than the slot. On a phone it wraps, because there is no
width to scroll into.
