# Web verification · the `V-*` rules

The static rules (`W-*`, `scripts/check_web.py`) read the built HTML. The
measured rules (`V-*`) read the page a browser actually laid out. The two sets
are separate on purpose: a measurement that judged itself would be a checker
grading its own work.

`scripts/web_measure.py` reports what Chromium computed. `scripts/web_verify.py`
compares that report with `plan.json` and says PASS, REVIEW, FAIL or SKIP.

```bash
python3 scripts/web_measure.py --series <series> --viewports 390,768,1024,1414
python3 scripts/web_verify.py --series <series>
```

Both read `dist/web/<series>/`; the builder writes `plan.json` beside the pages.
The browser half runs in the nightly job, not on every push.

## Status vocabulary

- **PASS** — the page computes what the plan states.
- **FAIL** — the page disagrees with the plan, or with a rule that has no
  acceptable alternative. A FAIL stops the gate.
- **REVIEW** — the value is measured and printed, but the decision is a
  composition choice. It does not stop the gate.
- **SKIP** — the page has nothing the rule can judge (no captions, no figures,
  a width the rule does not apply to).

## The rules

| Rule | Statement | Measured | Failure policy |
|---|---|---|---|
| `V-PLAN-01` | Computed type equals the plan at every role | font size, leading, weight, tracking per role | FAIL on drift beyond 0.5px; a role the page does not render is named in the detail, not failed |
| `V-PLAN-02` | The prose column is the planned column | prose box width against `plan.viewports[n].column` | FAIL; a measure cap may narrow the prose only within the plan's tolerance |
| `V-PLAN-03` | The figure spans its band | plate box width against the band | FAIL |
| `V-FIG-13` | One plate per figure is shown, and it is this width's class | visible plate count and its `data-folio-plate` | FAIL |
| `V-FIG-12` | The plate's type lands where the plan says, title included | delivered tier px from the plate width, title between H3 and 0.9 × H2 | REVIEW: the composition is a drawing fact, not a page defect |
| `V-FIG-14` | Each caption hangs from its plate | caption `left` / `width` against the figure's box | FAIL; a caption in the margin is a defect, not a note |
| `V-TYPE-02` | The prose runs the page's own column | every running paragraph's width against the chapter column | FAIL; a paragraph narrower than the column is a hole beside the text |
| `V-COL-01` | Text clears its contrast ratio | computed colour against the first opaque background, per role | FAIL below 4.5:1 (3:1 for large text) |
| `V-RHYTHM-01` | Every block gap is a step on the space scale | gaps between top-level chapter blocks | REVIEW; chapter boundaries are composed, not a spacing step |
| `V-OVF-01` | Nothing overflows sideways that the page did not mark | scrollers vs the document width | FAIL |
| `V-DOM-01` | The browser's blocks are the model's blocks | rendered block count against the page model | FAIL |

## Widths

The measured widths are review widths, not breakpoints: `390`, `768`, `1024`,
`1414`. The breakpoints themselves are tested at their boundaries by the plan.

## What the rules do not cover

- **Line length.** A character band would have to decide whether a longer line
  is a defect or a composition choice; that decision is not made yet, so the
  page prints the numbers in the rhythm and figure reports instead of failing.
- **Script rules.** Whether Chinese prose is indented and justified belongs to
  the content model (a `lang` on the block), which the page does not yet carry.
- **Widows.** `text-wrap` is a browser hint; the engine reports the plate and
  the column, not the last line's length.
