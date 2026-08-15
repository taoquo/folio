# ADR 0004: Renderer Consumes ResolvedScene

Status: Accepted

The architecture SVG renderer accepts only ResolvedScene. Focus, importance, node archetype, edge channel, typography, theme, and arrow geometry are resolved upstream. The renderer performs escaping and SVG serialization only.
