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
6. `web-verification.md` — the `V-*` rules: what each one measures, in which
   browser, and what it does when the page disagrees with the plan.

## Case or fixture

A page is one of two things, and `series.json` says which with `kind`.

- **`case`** is content. It names the work it reads (`source`: work, author,
  year, link) and it does not describe the engine that set it.
- **`fixture`** is the engine's conformance page. It carries a delivery status
  and a package path, and it is allowed to be about the engine because that is
  what it tests.

## Rule ids

A rule is `W-<area>-<n>`, stable, and reported by `scripts/check_web.py`.
Areas: `DLV` delivery, `STR` structure, `CNT` content, `TXT` text, `DEN`
density, `COL` colour, `FIG` figures, `GEO` geometry, `ACC` acceptance.

`scripts/web_geometry.py` is the figure-measurement helper behind `W-GEO-*`; it
does not report rule ids of its own.

The browser rules are `V-<area>-<n>`, reported by `scripts/web_verify.py` and
listed in `web-verification.md`.

## Commands

```bash
python3 scripts/build_web.py --series <dir>                 # build dist/web/<series>/
python3 scripts/build_web.py --series <dir> --verify         # build and check
python3 scripts/build_web.py --series <dir> --theme folio-forest-v1
python3 scripts/build_web.py --series <dir> --strict-figures # treat DSL advisories as failures
python3 scripts/check_web.py <page.html> --level 1           # CI gate
python3 scripts/check_web.py <page.html> --level 3 --source <source.txt>
python3 scripts/web_geometry.py <page.html>                  # figure geometry only
```

Build and check are separate commands: the browser measurement is the slow
half and belongs in the nightly job, not in the build.

```bash
python3 scripts/folio.py web --series <dir>
python3 scripts/check_web.py dist/web/<series>/<module>/index.html --level 3 \
  --series-dir dist/web/<series> --figures-manifest dist/web/<series>/figures.manifest.json
```

Two series are tracked, and CI builds both:

- `references/fixtures/web/reading-demo/` — `kind: fixture`, the conformance
  page. A change to the profile, the template or the contracts shows up here.
- `references/fixtures/web/attention/` — `kind: case`, a real reading page
  (`Attention Is All You Need`). It is the page a reader would open.

```bash
python3 scripts/folio.py web --series references/fixtures/web/reading-demo
python3 scripts/check_web.py dist/web/reading-demo/reading/index.html \
  --level 3 --source references/fixtures/web/reading-demo/source.txt \
  --series-dir dist/web/reading-demo
```

The series language comes from `series.json` (`"language": "en"` for an English
page); `references/profiles/web/folio-v1.yaml` supplies the matching font stack
and screen scale. The builder embeds the profile's face under `<out>/fonts/`
and points at it relative to each page's depth.

Levels follow C4: L1 structure, text, delivery and the figure contract (no
browser); L2 adds declared density and colour; L3 adds the host's figure
geometry audit.

## Non-goals

No component library, no router, no state machine, no forms, no dark-mode
switch, no client-side rendering. A page is a document that happens to reflow.
