# Web acceptance

## 1. Workflow

1. Read the source; fix the chapter skeleton from it, do not impose a template.
2. Search the principle layer when the source states a convention.
3. Check the repository: which engine code, which theme role, which gate.
4. Build the skeleton, write the chapters, add one figure per mechanism.
5. Run the machine audits to zero.
6. Deploy the module to its own URL.
7. Verify the index and the module page together.

Steps 1–5 happen in the repository. Step 6 is the only step that needs a host.

## 2. The 16 acceptance items

| # | Item | Kind | Rules |
|---|---|---|---|
| 1 | Source sections, tables, code and numbers are all present | machine | W-CNT-01 |
| 2 | Every scanned text feature is componentized, and every top-level block is a declared role with a unique id | machine | W-CNT-02, W-STR-05, W-STR-06 |
| 3 | No list-header block, no long block, no multi-clause block, no duplicate block | semi | W-CNT-03/04 |
| 4 | No status row, identity KPI row or evidence note after the head | machine | W-STR-02 |
| 5 | Table cells vertically centred; no arrow flows inside cells | machine | W-DEN-05/07 |
| 6 | Figure contract: kind, composition, node tier, metadata, caption, every drawn type tier recorded, the plate filled by the drawing, and its delivered size reported | machine | W-FIG-01/03/05/06/09/10/11/12 |
| 7 | Geometry audits at zero (DSL diagnostics + host) | machine | W-GEO-01 |
| 8 | Chapter and figure numbers continuous, no collisions | machine | W-TXT-02/02b |
| 9 | No banned symbol in any title | machine | W-TXT-01 |
| 10 | Anchors resolve, no external script, external links reachable | machine | W-ACC-10, W-DLV-01b |
| 11 | L1/L2 colour compliance; every variable defined; the template decides no value; every semantic mark names a meaning; at most four colours per figure | machine | W-COL-01/02/06/07, W-DEN-08/09 |
| 12 | A case names the work it reads (work, author, year, link); a fixture is exempt | machine | W-CNT-05 |
| 13 | Reading rail: one tick per chapter, active on scroll, title on hover | semi | W-DLV-06/07/08 |
| 14 | Every figure traces to a DSL fixture and hash | machine | W-FIG-07 |
| 15 | Figures are DSL products with zero ERROR diagnostics | machine | W-GEO-01 |
| 16 | Online verification pass | manual | — |

Twelve items are machine-decided, three are machine-assisted with a human
verdict, one is manual. A page that cannot state which kind an item is has not been
designed for verification.

## 3. Levels (C4)

| Level | Runs | Needs | Where |
|---|---|---|---|
| L1 | structure, text, delivery, links, the figure contract | Python only | CI fast gate |
| L2 | declared density and colour, content coverage | Python only | CI or nightly |
| L3 | the figure geometry audit (W-GEO-01) | Python only, static SVG | nightly or before publish |
| L4 | the page computes what its plan says, in a browser | Chromium (Playwright) | nightly |

L1–L3 need no browser, and a page never fails for want of one. L4 is the only
level that measures the rendered page: the plan states what each width must
compute to, `web_measure.py` records what Chromium computed, and `web_verify.py`
compares them. The plan is arithmetic over the profile, so L4 is verifiable
without a screenshot and cannot drift with anti-aliasing or a browser upgrade.

WeasyPrint is not an L4 oracle. It is a print formatter: it ignores
`@media (min-width/max-width)` and applies `@media print`, so measuring a
responsive page with it reports one layer at every width.

## 4. Commands

```bash
python3 scripts/build_web.py --series <dir> --verify --level 3 --source <source.txt>
python3 scripts/check_web.py <page> --level 1          # the CI gate
python3 scripts/web_geometry.py <page>                 # figures only
python3 scripts/web_plan.py --series <name> --gate     # the layout plan, arithmetic only
python3 -m unittest tests.test_web_contracts

# L4, where a browser is allowed
python3 scripts/web_measure.py --series <name>         # what Chromium computed
python3 scripts/web_verify.py --series <name>          # what the plan required
```

A failing rule prints its `W-*` id. An id that no rule owns is a defect in this
directory, not in the page.
