# 0009. The host owns the stage

## Status

Accepted.

## Context

A web figure is delivered in a column, not on a page: the reading page hands a
plate 335 to 760 CSS pixels depending on the viewport class. A drawing's type
is expressed in stage units (7 / 9 / 12), so the same 960-unit plate delivered
at 335px renders its smallest tier at 3.4px. Enlarging the plate does not help
— it scales the type and the empty margin together.

Two shortcuts were rejected. A payload `width` field would let an author change
the drawing's units to fit one column, which is the pixel-level intent ADR 0001
forbids, and the artifact and the catalog still need the authored 960 stage. A
CSS transform would scale the plate without moving its composition, leaving
the rows wrapped for a width the reader never sees.

## Decision

The stage is a host input, never a payload field.

- `drawing/stage.py` defines `StageSpec`: 240–960 units, a multiple of 4, with
  960 as the default. `compile_payload(..., stage=...)` takes it; a payload
  that declares `width` fails with `CP002`.
- Only the families listed in `STAGE_AWARE` may be compiled on another stage.
  Today that is `architecture`, `state-machine` and `swimlane`, each of which
  was measured across the ladder before it was added. A family outside the set
  fails with `CP004` rather than silently ignoring the request.
- Geometry scales with the stage; the type scale does not. Chrome — padding,
  gaps, gutters, node boxes — is authored in stage units and is scaled; the
  type tiers stay at 7 / 9 / 12, so the type-to-stage ratio rises as the stage
  falls. That is what makes a narrow band legible.
- The host chooses the stage by measurement, not by arithmetic:
  `web_figures.compose_for_band()` walks the ladder and keeps the **largest**
  stage that clears both the delivered-type floor and the plate-shape band.
- The default stage is the identity composition. `scaled(1.0)` returns the
  authored geometry, so the artifact and the catalog do not move for a reason
  of their own.

## Consequences

A plate composed for a band is delivered at that band, so the contract holds a
*shape* (framed height over width, 0.45–1.60) rather than a pixel height:
scaling preserves shape. Each plate is framed to its ink, and the figure
manifest records the stage, the framed box, every drawn tier and the delivered
size, so the reading page's checks can recompute what the reader gets instead
of trusting a stylesheet.

The stage mechanism makes the *composition* the host's decision, so a family
that regresses on one stage is now a build failure rather than a fallback:
`CP005` when no stage satisfies both obligations, and `SW024` when a swimlane's
lane stack cannot be drawn at all. Both are budgeted errors, not warnings.

Adding a family to `STAGE_AWARE` is a measured claim, not a declaration. The
regression that closed the initial work is `tests/test_drawing_stage.py`: each
family is compiled across 240–960 and must report no ERROR at any stage it
accepts.
