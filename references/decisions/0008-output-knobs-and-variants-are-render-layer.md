# 0008. Output knobs and render variants live in the render layer

## Status

Accepted.

## Context

V5 introduced four presentation controls: export size, detail level, audience, and render variant. Each of them is a plausible payload field. A `bar-chart` payload could carry `detail: "essential"`, and a `flowchart` payload could carry `variant: "sketchy"`.

Allowing that would break two existing guarantees. First, the same semantic input would no longer produce one canonical drawing, so catalog baselines and host digests would fork per presentation choice. Second, the chart compilers enforce a strict field whitelist; widening it for presentation keys would let pixel-level intent leak back into agent-produced payloads, which ADR 0001 forbids.

## Decision

Size, detail, audience, and variant are render-layer concepts. They live in `scripts/drawing/output/` and are never valid payload fields.

- `size` is consumed only by the rasterizer. It selects an export width and does not reach the compiler.
- `detail` and `audience` are applied to the resolved scene inside `_finalize`, after retheming and before validation, so every quality gate runs against the scene that actually ships.
- `variant` is applied at serialization time in `render_svg` as an additive scoped `<defs>` block.

Payload schemas stay closed. Adding any of these keys to a payload fails with `ERROR BC000: unknown field`.

## Consequences

Scene identity is preserved. `detail` may remove gridlines and annotations, but it rewrites `reading_order` in the same pass, so `AX200`-`AX203` hold. `audience` may raise a font size, but it cannot add elements. No knob may introduce an accent-bearing element, so the single-accent invariant from ADR 0006 survives every combination.

Validation order is fixed: retheme, then knobs, then the five validators. A knob can therefore never smuggle an invalid scene past a gate.

Two degradations are accepted and documented rather than hidden:

- `page-preview` renders a fixed A4 raster, so it ignores `size` and warns.
- `motion` is CSS-driven, so PNG and PDF exports are byte-identical to `plain` and the CLI warns.

Because these are flags and not payload fields, an existing fixture renders unchanged under default flags, and the 22 kinds cross all 3 detail levels and all 3 audiences with zero diagnostics.
