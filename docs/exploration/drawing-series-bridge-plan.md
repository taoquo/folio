# Implementation plan: making the drawing series palette follow the scheme

Route A, from `drawing-series-bridge.md`. The goal is that a document colour
scheme reaches a standalone diagram's **series colours**, which today it reaches
only for the first two positions.

**Definition of done**

1. A scheme's six series colours drive every chart the drawing compilers emit.
2. The default scheme's output is **unchanged**, in all three drawing themes.
3. A scheme that cannot be bridged safely is **rejected with a reason**, not
   silently drawn.

---

## Facts the plan rests on

| Fact | Measured |
|---|---|
| Series colours are 6 named tokens | `brand`, `olive`, `label`, `neutral_mid`, `neutral_light`, `neutral_deep` |
| Painted from | 3 call sites, `dataviz.py:684` `:887` `:995` |
| Already following a scheme | 3 of 6 (`brand`, `olive`, `brand_tint`) |
| Chart-only tokens | `neutral_mid`, `neutral_light`, `neutral_deep` — 9 uses, all in `dataviz.py` |
| All three themes define all 12 tokens | dark and terminal need **no new values authored** |
| The swap keys by colour value | `theme_token_map`, so same-value source fields collapse |
| Same-value groups today | **0** in all three themes; a test now asserts it |
| Palette coverage | 4 of the 6 series values already exist; 2 are new |

---

## The shape

Six new tokens on `FolioTheme`, named for the chart that uses all six — the donut,
which paints them in order. The two other charts take a subset.

| New token | Copies today's | folio | dark | terminal | On canvas |
|---|---|---|---|---|---|
| `series_1` | `olive` | `#5A4A43` | `#E2D3C6` | `#C7E6D2` | 7.44:1 |
| `series_2` | `label` | `#74665F` | `#C9B7A9` | `#A9D2B8` | 4.88:1 |
| `series_3` | `neutral_mid` | `#B9ACA3` | `#A99383` | `#8FB49E` | 1.96:1 |
| `series_4` | `neutral_light` | `#D7CBC2` | `#8A7565` | `#6F9280` | 1.41:1 |
| `series_5` | `brand_tint` | `#F7E6E1` | `#4A2A22` | `#1D3A2B` | 1.07:1 |
| `series_6` | `neutral_deep` | `#8B8078` | `#CBBAAB` | `#B6D9C3` | 3.40:1 |

**Every value is copied from the token it replaces**, so all three themes render
identically. What changes is where `folio`'s six values *come from*: a document
role instead of a literal.

### The obligation each position carries

| Position | Painted as | Minimum |
|---|---|---|
| 1, 2, 6 | 1.6px stroke in a line chart, and a bar fill | **3:1** non-text contrast on the canvas |
| 1–5 | donut and bar fill, always beside a labelled key | none, but must be distinguishable |

Classic clears the stroke rule at 7.44, 4.88 and 3.40. That the lightest three are
fills behind a key is what lets 1.96 and 1.41 ship; a scheme that treated all six
as interchangeable would put an invisible line on a page, so the rule is stated
and checked rather than assumed.

### Why the six are aliases in dark and terminal

`theme_token_map` keys by colour value. In `folio`, `series_1` and `olive` hold
the same value, so the map has one entry for `#5A4A43` — and dark's `series_1`
must therefore equal dark's `olive`. It does, because that is where the value came
from. Writing them as aliases keeps the map a function in every theme pair.

This means dark and terminal get nothing new; they keep exactly the charts they
have. Giving them their own series palettes is a later, separate decision, and
would need values distinct from every other token in each theme.

---

## Phase 1 — the drawing tokens

**`scripts/drawing/theme/folio.py`**

- Add `series_1` … `series_6` to `FolioTheme`, after the existing colour fields
  and before `serif`, so `asdict` order is stable and `theme_token_map` sees them.
  Defaults are the six values above.
- Extend `_SHARED_WITH_DOCUMENT`:

  ```python
  "series_1": "color.series.1",   # … through series_6
  ```

**`scripts/drawing/theme/profiles.py`**

- `DARK_THEME` and `TERMINAL_THEME`: add the six fields as aliases of the token
  each replaces.
- Extend `_GRAPHIC_ON_SURFACE` with the three stroked positions:

  ```python
  ("series_1", "parchment", GRAPHIC_MINIMUM, "series 1 stroke on canvas"),
  ("series_2", "parchment", GRAPHIC_MINIMUM, "series 2 stroke on canvas"),
  ("series_6", "parchment", GRAPHIC_MINIMUM, "series 6 stroke on canvas"),
  ```

  `contrast_violations` then rejects a scheme whose series would be invisible as a
  line — which is the failure this whole phase exists to prevent.

**Verification**: `python3 -m unittest tests.test_drawing_theme_v5` — the token
test moves from 12 to 18 colours, and the bridge and function tests still pass.

---

## Phase 2 — the document roles

**`references/profiles/theme/folio-classic-v1.yaml`**

Two palette entries, named by the ladder rule (`python3 scripts/check_palette_scale.py`
is the judge):

| Entry | Value | Luminance | Band | Why that number |
|---|---|---|---|---|
| `warm-650` | `#74665F` | 0.140 | 600 | band 600 is held by `warm-600` (0.150), so the darker one steps up |
| `warm-250` | `#D7CBC2` | 0.611 | 200 | band 200 is held by `warm-200` (0.717), so the darker one steps up |

Six roles, with a comment stating that a series has no meaning beyond being a
different series:

```yaml
series:
  1: {palette: warm-700}      # matches text.secondary, so the default is unchanged
  2: {palette: warm-650}
  3: {palette: warm-350}
  4: {palette: warm-250}
  5: {palette: cinnabar-100}  # matches accent.brand-tint
  6: {palette: warm-500}
```

**Verification**: `profile_check.py`, `check_palette_scale.py`, and
`projection.py check` -- which will name `--color-series-*` as projected and
unread, which is correct until Phase 5 gives them a reader.

`REQUIRED_ROLES` is **not** extended here. Doing so would fail the two
demonstration schemes one step before the phase that gives them series colours,
so the requirement moves to Phase 4.

---

## Phase 3 — the call sites

**`scripts/drawing/dataviz.py`**, three lines:

| Line | Today | Becomes |
|---|---|---|
| 684 | `(theme.olive, theme.label, theme.neutral_mid)` | `(theme.series_1, theme.series_2, theme.series_3)` |
| 887 | `(theme.olive, theme.label, theme.neutral_deep)` | `(theme.series_1, theme.series_2, theme.series_6)` |
| 995 | `(theme.olive, theme.label, theme.neutral_mid, theme.neutral_light, theme.brand_tint, theme.neutral_deep)` | `(theme.series_1, …, theme.series_6)` |

The `min(series_index, 2)` clamp at `:689` and `:889` is unchanged.

**Verification**: every diagram SVG must be **byte-identical** to the committed
one. This is the phase's real test, and it is exact:

```bash
python3 scripts/build.py
git diff --stat assets/diagrams/generated/svg
```

---

## Phase 4 — the demonstration schemes

`folio-slate-v1` and `folio-forest-v1` need six series colours each, or the
scheme check fails them.

**`scripts/scaffold_theme_scheme.py`** generates them from the ramp it already
computes, mirroring the classic structure:

| Role | From |
|---|---|
| `series.1` | the scheme's `text.secondary` |
| `series.2` | a new mid-dark step, band-named |
| `series.3` | `border.default` |
| `series.4` | `border.soft` |
| `series.5` | `accent.brand-tint` |
| `series.6` | `text.muted` |

`darken_until` is applied to `series.1`, `series.2` and `series.6` at the 3:1
floor, so a generated scheme cannot fail the new rule. The committed profiles are
regenerated, and the test that compares them to the generator keeps them honest.

**`scripts/check_theme_schemes.py`** — now that every scheme carries the six, add
them to `REQUIRED_ROLES`, so one that omits them fails rather than falling back
to a literal. The three built-in themes' series values clear the new stroke rule
(the weakest is `folio`'s `series_6` at 3.40:1 against a 3.0 floor), so extending
`_GRAPHIC_ON_SURFACE` in Phase 1 accepts all of them.

---

## Phase 5 — the checks

**`scripts/check_theme_schemes.py`** gains a bridge rule:

> Build the drawing theme from the scheme, then require
> `theme_token_map(folio_from_scheme, dark)` to be a **function** — no source
> value may map to two targets.

This is the rule that makes the aliasing safe, and it is what would reject a
scheme that set a series colour equal to, say, `parchment`.

**`scripts/projection.py`** — `--color-series-*` will be projected and read by no
template, because the drawing theme reads them through `style_resolver`, not
through CSS. They belong in `UNCONSUMED` **with that reason**, alongside the
typography metrics. The consumption gate stays honest by naming the reader.

**`scripts/color_sources.py`** — the drawing theme's `series_*` tokens join the
shared-meaning table, so a scheme that disagrees with itself is reported there
too.

---

## Phase 6 — verification

Run in this order, and stop at the first failure:

```bash
python3 -m unittest discover -s tests            # 979 + new
python3 scripts/build.py                         # rebuild every artifact
git diff --stat assets/diagrams/generated/svg    # must be empty
python3 scripts/document_baseline.py compare     # must match
python3 scripts/profile_check.py
python3 scripts/projection.py check
python3 scripts/color_sources.py check
python3 scripts/check_palette_scale.py
python3 scripts/check_theme_schemes.py
python3 scripts/build_static_theme.py --check
python3 scripts/build_scheme_comparison.py --check
python3 scripts/build.py --check --sync --verify --check-placeholders --check-index --check-rhythm
ruff check .
```

Then the capability itself, which is the point:

```bash
FOLIO_THEME=folio-slate-v1 python3 scripts/build.py diagram-bar-chart diagram-donut-chart
# the two charts' series colours must be the slate scheme's, not the classic ones
```

and the round trip — build with slate, restore the default, rebuild: the SVGs
must return byte-identical.

---

## Phase 7 — documentation

| File | Change |
|---|---|
| `references/design.md` | replace the "chart colour belongs to the drawing theme" note: the six series positions now follow the scheme; state the stroke obligation |
| `docs/exploration/drawing-series-bridge.md` | add an outcome section; the analysis stays as the record of why |
| `AGENTS.md` | `references/profiles/theme/` description mentions series; the change rule for a new colour notes the two extra entries |
| `README.md` / `README.zh-CN.md` | the colour-schemes section says a scheme reaches chart series; a new scheme needs six more colours |
| `CHEATSHEET.md` | the six series roles, with their stroke/fill obligation |

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| A copied value is wrong, so a chart changes | Low | The SVG byte-comparison in Phase 3 catches any difference, in all 23 types |
| A scheme breaks the swap map | Medium | The function rule in Phase 5 rejects it; the aliasing keeps dark and terminal consistent |
| The default output shifts through a rounding or ordering difference | Low | `asdict` order is preserved by appending fields; the diagram baseline and the document baseline both gate it |
| Scheme authors must now supply six more colours | Certain | `scaffold_theme_scheme.py` generates them and solves for the contrast floor |
| The lighter three positions are visually weak as fills | Pre-existing | Unchanged by this work; recorded, and a scheme may now improve them |

## Rollback

Each phase is a separate commit. Phases 1–3 are the bridge and revert together:
restoring the three `dataviz.py` lines returns every chart to the drawing theme's
own tokens, and the six document roles become inert rather than wrong. Phase 1
alone is safe to keep — six tokens that nothing reads yet.
