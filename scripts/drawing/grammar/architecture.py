from __future__ import annotations

from dataclasses import dataclass, field

from .base import SpacingGrammar


@dataclass(frozen=True)
class ArchitectureGeometryGrammar:
    grid: int = 4
    node_width: int = 176
    node_height: int = 72
    node_gap: int = 48
    layer_gap: int = 96
    edge_node_gap: int = 24
    edge_edge_gap: int = 18
    padding: str = "[top=80,left=96,bottom=72,right=96]"
    node_radius: int = 5
    group_radius: int = 10
    group_pad_x: int = 20
    group_pad_top: int = 24
    group_pad_bottom: int = 20
    arrow_size: int = 8
    size_tiers: tuple[tuple[str, int, int], ...] = (
        ("compact", 144, 64),
        ("regular", 176, 72),
        ("wide", 224, 80),
    )


@dataclass(frozen=True)
class ArchitectureGrammar:
    geometry: ArchitectureGeometryGrammar = field(default_factory=ArchitectureGeometryGrammar)
    spacing: SpacingGrammar = field(default_factory=SpacingGrammar)
    composition_patterns: tuple[str, ...] = ("layered", "pipeline", "hub")
    axes: tuple[str, ...] = ("top-down", "left-right")
    node_archetypes: tuple[str, ...] = ("component", "datastore", "external", "cloud")
    edge_channels: tuple[str, ...] = ("primary-flow", "secondary-flow", "async-flow")
    emphasis_levels: tuple[str, ...] = ("focal", "normal", "background")
    region_treatments: tuple[str, ...] = ("layer-band", "soft-boundary", "trust-boundary", "phase-band", "none")
    pictograms: tuple[str, ...] = (
        "client", "gateway", "compute", "queue", "database", "cache",
        "storage", "cloud", "security", "observability", "network", "external-system",
    )


DEFAULT_ARCHITECTURE_GRAMMAR = ArchitectureGrammar()
