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
| 2 | Every scanned text feature is componentized | machine | W-CNT-02 |
| 3 | No list-header block, no long block, no multi-clause block, no duplicate block | semi | W-CNT-03/04 |
| 4 | No status row, identity KPI row or evidence note after the head | machine | W-STR-02 |
| 5 | Table cells vertically centred; no arrow flows inside cells | machine | W-DEN-05/07 |
| 6 | Figure contract: kind, composition, node tier, metadata, caption | machine | W-FIG-01/03/05/06/09 |
| 7 | Geometry audits at zero (DSL diagnostics + host) | machine | W-GEO-01 |
| 8 | Chapter and figure numbers continuous, no collisions | machine | W-TXT-02/02b |
| 9 | No banned symbol in any title | machine | W-TXT-01 |
| 10 | Anchors resolve, no external script, external links reachable | machine | W-ACC-10, W-DLV-01b |
| 11 | L1/L2 colour compliance; every variable defined; every semantic mark names a meaning; at most four colours per figure | machine | W-COL-01/02/06/07 |
| 12 | Evidence: file:line, sources, engine-comparison section | semi | W-CNT-05 |
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
| L1 | structure, text, delivery, links | Python only | CI fast gate |
| L2 | declared density and colour, content coverage | Python only | CI or nightly |
| L3 | figure geometry | Python only, static SVG | nightly or before publish |

The browser is optional and never required for a page to pass L1. When a
browser-based pass exists it adds the landing details listed in
`web-figures.md`; it does not replace the static audits.

## 4. Commands

```bash
python3 scripts/build_web.py --series <dir> --verify --level 3 --source <source.txt>
python3 scripts/check_web.py <page> --level 1          # the CI gate
python3 scripts/web_geometry.py <page>                 # figures only
python3 -m unittest tests.test_web_contracts
```

A failing rule prints its `W-*` id. An id that no rule owns is a defect in this
directory, not in the page.
