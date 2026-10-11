# Can the drawing theme's series colours be bridged?

The short answer: **yes, and it is cheaper than the earlier note in
`references/design.md` claimed. It also buys nothing for this project, which
builds with the default scheme, so the recommendation is to keep the design and
not build it yet.**

The earlier note said connecting the two themes meant "extending all three
drawing themes at once". That was wrong, and measuring it is what shows why.

---

## 1. The series palette is not scattered literals

A chart's series colours are six named drawing-theme tokens:

| Position | Token | Used by |
|---|---|---|
| 1 | `brand` | the focus series, in every chart |
| 2 | `olive` | bars, lines |
| 3 | `label` | bars, lines |
| 4 | `neutral_mid` | bars, donut |
| 5 | `neutral_light` | donut |
| 6 | `brand_tint` | donut |

Three call sites in `scripts/drawing/dataviz.py`:

```python
palette = (theme.olive, theme.label, theme.neutral_mid)                    # bars
palette = (theme.olive, theme.label, theme.neutral_deep)                   # lines
palette = (theme.olive, theme.label, theme.neutral_mid,
           theme.neutral_light, theme.brand_tint, theme.neutral_deep)      # donut
```

The first series is always `theme.brand`, so positions 1 and 2 arrive through the
focus series rather than through the tuple.

**Every one of the twelve tokens is already defined in all three themes**, and
has been since the swap unit was written:

```
DARK_THEME = FolioTheme(parchment=…, ivory=…, …, neutral_deep="#CBBAAB")
TERMINAL_THEME = FolioTheme(…)
```

So dark and terminal need **no new values authored**. That was the cost the
earlier note was worried about, and it does not exist.

---

## 2. Half the series palette already follows a scheme

The document theme and the drawing theme share seven tokens. Three of the six
series positions sit on shared tokens:

| Position | Token | Source today |
|---|---|---|
| 1 | `brand` | follows `color.accent.brand` |
| 2 | `olive` | follows `color.text.secondary` |
| 3 | `label` | fixed, drawing-only |
| 4 | `neutral_mid` | fixed, drawing-only |
| 5 | `neutral_light` | fixed, drawing-only |
| 6 | `brand_tint` | follows `color.accent.brand-tint` |

**3 of 6 already move when the scheme moves.** Selecting a scheme changes a
diagram's first two series and the donut's last segment today.

`neutral_mid`, `neutral_light` and `neutral_deep` are chart-only: nine uses
across the whole drawing package, every one of them in `dataviz.py`. They are
already dedicated series colours, just named as if they were a neutral ramp.

`olive`, `label` and `brand_tint` are **not** chart-only — `olive` alone is used
37 times, thirteen of them as text in `roles.py`. They cannot be repurposed for
series, so a bridge needs new tokens rather than reusing these.

---

## 3. Found while measuring: a bridge that had silently broken

`_SHARED_WITH_DOCUMENT` mapped `brand_tint` to `color.accent.tint`. That role was
renamed to `color.accent.brand-tint` when the tint spellings were unified, and the
mapping was not.

The consequence was invisible: `style_resolver` returned nothing, the entry was
dropped from the result, and the field fell back to its literal. In the default
scheme the literal and the role hold the same value, so the diagram looked right —
and would have kept looking right while every *other* scheme left the accent tint
on the default red.

Fixed, plus a test that every mapped role resolves, plus `FOLIO_STRICT_THEME=1`
for a caller that would rather fail than fall back.

---

## 4. The real constraint: the swap keys by colour value

`theme_token_map` builds `{source_value: target_value}`:

```python
for key, value in asdict(source).items():
    if isinstance(value, str) and value.startswith("#"):
        mapping[value.lower()] = target_tokens[key]
```

The scene stores concrete colour strings, not the token a colour came from. So
two fields holding the **same** value in the source collapse into one entry, and
the later field in dataclass order wins.

Today that never happens: all three themes have **zero same-value groups**, which
is what makes the map a clean bijection. That property is load-bearing and was
never written down.

The failure mode is real, and a controlled experiment shows it. Give
`muted_stroke` the value of `neutral_mid`:

```
目标里 muted_stroke = #8A7568
目标里 neutral_mid  = #A99383
映射 #B9ACA3 -> #A99383      （只有一个赢家）
```

One of the two silently loses its meaning, and which one depends on the order the
fields happen to be declared in.

**Why this matters for the bridge**: adding `series_1..6` with today's values
creates six same-value groups, because each series token would equal the token it
is standing in for. That is safe only if every theme gives the colliding pair the
same value.

---

## 5. Two routes

### Route A — dedicated series tokens, values constrained

Add `series_1..6` to `FolioTheme`. In the `folio` profile they read six new
document roles; in dark and terminal each is set equal to the token it collides
with, which keeps the swap a function and keeps both themes' charts
byte-identical.

| Step | Work |
|---|---|
| `FolioTheme` | 6 new fields |
| `profiles.py` | 12 values, copied from the tokens they stand in for |
| `_SHARED_WITH_DOCUMENT` | 6 entries |
| `dataviz.py` | 3 call sites |
| document profile | 6 `series.*` roles, 2 new palette entries (`#74665F`, `#D7CBC2`) |
| checks | the function rule (added), plus series 1-3 must clear 3:1 for 1.6px line strokes |

Default output: **unchanged**, in all three themes.
Cost: moderate, mechanical, and every step is verifiable against the existing
diagram baselines and the contrast table.

**The catch**: series 1-3 are stroked at 1.6px in line charts, so a scheme that
supplies them must clear WCAG non-text contrast. Positions 4-6 are fills that
always ship beside a labelled key, which is why `neutral_mid` and `neutral_light`
get away with 1.9:1 and 1.35:1 today. A scheme that treated all six as
interchangeable would put an invisible line on the page, so the bridge would need
to state which positions carry which obligation.

### Route B — make the swap key on token identity

Thread the token name through the scene so a retheme is a name lookup rather than
a value lookup. This removes the collision hazard entirely and lets dark and
terminal have their own dedicated series palettes.

It also means touching the scene model and every compiler that paints, across 23
diagram types. The payoff is a class of bug removed, not a feature delivered.

---

## 6. Verdict

**Feasible, and Route A is the right shape if it is done.** Nothing blocks it:
the values exist in all three themes, the default output would not move, and the
one hazard is a property that can be checked — and now is, by a test.

**But it should not be built yet, and this is the deciding argument:**

- This repository builds with the default scheme. Bridging changes nothing for
  anything it publishes.
- Three of six series positions already follow a scheme. The three that do not are
  `label`, `neutral_mid` and `neutral_light`, and the latter two are fills behind
  a labelled key — the least visible part of a chart.
- Documents that draw charts already follow. Their charts are drawn inline with
  literals the ledger maps to palette entries, so an equity report's series
  colours move with the scheme today. The gap is **standalone diagram artifacts**
  only.
- It touches the drawing core, where 23 diagram types and an approved visual
  baseline sit, to deliver a capability no current artifact exercises.

**Do it when** a scheme other than the default is adopted for content that
includes standalone diagrams, or when a scheme needs a series palette that is
deliberately distinguishable rather than the drawing theme's muted neutrals.

Until then the honest position is the one now in `references/design.md`: a
document scheme reaches a diagram through the seven shared tokens, the series
palette belongs to the drawing theme, and the bridge is a designed change rather
than an oversight.

---

## Outcome

Built. Six series tokens on the drawing theme, read from `color.series.*` for the
`folio` profile and aliased to their old tokens in dark and terminal; three call
sites; six document roles; a rule that rejects a scheme whose swap map stops being
a function; and a ledger that records what a literal *means* rather than which
palette entry it happened to match.

The default scheme renders byte-identically -- every generated SVG is unchanged --
and the measurement is the same chart built in each scheme, in
`docs/acceptance/series-by-scheme.png`, with the whole report in
`docs/acceptance/document-by-scheme.png`.

## Reproduce

```bash
# which series positions follow a scheme, and which do not
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from drawing.theme.folio import shared_from_document_theme
print(sorted(shared_from_document_theme()))"

# the swap must stay a function; this is the test that says so
python3 -m unittest tests.test_drawing_theme_v5.DrawingTokenBridgeTests
```
