# ADR 0002: Use Three Intermediate Representations

Status: Accepted

Architecture generation uses SemanticDiagram for meaning, DrawingPlan for visual intent, and ResolvedScene for exact geometry and style. Each representation is JSON-serializable so semantic, design, and rendering regressions can be inspected separately.
