# Folio Web · reading pages

Scope: a reading page that a reader opens as a static file or a hosted URL. Two
page types only — a series index and a module archive. No workspace UI, no app
shell, no client framework, no build step at view time.

This scenario is the engine extended to the Web, not a second design system:

| Layer | Owner | Where |
|---|---|---|
| Colours, type sizes, line heights, spacing, radius, shadow, code block | engine | `references/design.md`, `references/profiles/theme/*.yaml` |
| Screen type scale, font stacks, spacing, radii, measure, page geometry | engine | `references/profiles/web/folio-v1.yaml`, `scripts/projection.py` |
| Figures | engine | `references/drawing-dsl.md`, `scripts/drawing/` |
| Delivery, structure, content components, density, audits, acceptance | this scenario | this directory |

Every value a page shows comes from the engine's profiles. A Web template that
writes a hex colour, a second type scale or a second code palette is wrong by
construction, not by taste. `scripts/projection.py check` rejects a literal in
`assets/templates/web/base.css`; `scripts/check_web.py` resolves the built
page's custom properties before it measures density.

## Reading order

1. `web-delivery.md` — what ships, the two skeletons, the closed vocabulary.
2. `web-content.md` — what goes on the page, how text becomes a component.
3. `web-visual.md` — density, measure, colour layers.
4. `web-figures.md` — the drawing-DSL host contract and the geometry audits.
5. `web-acceptance.md` — the seven-step workflow and the 16 acceptance items.

## Rule ids

A rule is `W-<area>-<n>`, stable, and reported by the same id from
`scripts/check_web.py` and `scripts/web_geometry.py`. Areas: `DLV` delivery,
`STR` structure, `CNT` content, `TXT` text, `DEN` density, `COL` colour, `FIG`
figures, `GEO` geometry, `ACC` acceptance.

## Commands

```bash
python3 scripts/build_web.py --series <dir>                 # build dist/web/<series>/
python3 scripts/build_web.py --series <dir> --verify         # build and check
python3 scripts/build_web.py --series <dir> --theme folio-forest-v1
python3 scripts/build_web.py --series <dir> --strict-figures # treat DSL advisories as failures
python3 scripts/check_web.py <page.html> --level 1           # CI gate
python3 scripts/check_web.py <page.html> --level 3 --source <source.txt>
python3 scripts/web_geometry.py <page.html>                  # figure geometry only
python3 scripts/folio.py web --series <dir> --verify         # the same build through the CLI
```

The tracked fixture is `references/fixtures/web/reading-demo/`; CI builds and
verifies it at level 3, so a change to the profile, the template, or the
contracts is caught before it reaches a page:

```bash
python3 scripts/folio.py web --series references/fixtures/web/reading-demo \
  --verify --level 3 --source references/fixtures/web/reading-demo/source.txt
```

The series language comes from `series.json` (`"language": "en"` for an English
page); `references/profiles/web/folio-v1.yaml` supplies the matching font stack
and screen scale. The builder embeds the profile's face under `<out>/fonts/`
and points at it relative to each page's depth.

Levels follow C4: L1 structure, text and delivery (no browser); L2 adds declared
density and colour; L3 adds figure geometry.

## Non-goals

No component library, no router, no state machine, no forms, no dark-mode
switch, no client-side rendering. A page is a document that happens to reflow.
