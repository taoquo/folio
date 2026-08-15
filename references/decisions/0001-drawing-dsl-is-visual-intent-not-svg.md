# ADR 0001: Drawing DSL Is Visual Intent, Not SVG

Status: Accepted

Folio represents composition, hierarchy, archetypes, edge channels, and region treatments in DrawingPlan. It does not expose coordinates, colors, font sizes, radii, or paths. This keeps authored intent reviewable and lets layout and rendering backends evolve independently.
