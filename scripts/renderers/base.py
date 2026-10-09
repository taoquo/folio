"""The renderer boundary.

A renderer turns a prepared request into artifacts. Nothing about WeasyPrint,
DOM trees or CSS boxes appears in this API: those are one engine's internals,
and a document model that leaks them cannot be handed to a second engine.

The API is deliberately small. Four calls cover the whole contract:

    probe()             what this engine is and what it can do
    validate_request()  may this request be rendered, and what degrades
    render()            produce the artifacts
    inspect()           read back what was produced

Capability reporting is graded rather than boolean, because "supports
footnotes" is not a yes-or-no question in practice. `unsupported` must fail a
hard requirement; `partial` or `emulated` must be recorded as a downgrade. The
one thing a renderer may never do is fall back silently.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

# native      the engine implements this as a first-class feature
# emulated    the engine can approximate it, with a recorded difference
# partial     supported for some inputs but not all
# unsupported not available at all
CapabilityLevel = Literal["native", "emulated", "partial", "unsupported"]

CAPABILITY_LEVELS: tuple[str, ...] = ("native", "emulated", "partial", "unsupported")

# Requirement strength. A hard requirement that cannot be met must fail before
# rendering; a soft one that cannot be met must produce a downgrade record.
RequirementStrength = Literal["hard", "soft"]


@dataclass(frozen=True, slots=True)
class RendererInfo:
    """What an engine is, and what it can do.

    Capability values must come from a conformance test against the engine that
    is actually installed. Copying them from documentation is how a manifest
    ends up describing a version nobody runs.
    """

    name: str
    version: str
    outputs: frozenset[str] = frozenset({"pdf"})
    capabilities: Mapping[str, CapabilityLevel] = field(default_factory=dict)

    def level(self, feature: str) -> CapabilityLevel:
        return self.capabilities.get(feature, "unsupported")

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "outputs": sorted(self.outputs),
            "capabilities": dict(sorted(self.capabilities.items())),
        }


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    """One feature a document needs, and how badly."""

    feature: str
    strength: RequirementStrength
    reason: str

    @property
    def is_hard(self) -> bool:
        return self.strength == "hard"


@dataclass(frozen=True, slots=True)
class Downgrade:
    """A requirement the renderer met by some other means.

    Recorded rather than swallowed. A document that loses its footnotes and
    still reports success is the failure mode this exists to prevent.
    """

    feature: str
    requested: str
    resolved: str
    reason: str
    severity: Literal["info", "warning"] = "warning"

    def to_json(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "requested": self.requested,
            "resolved": self.resolved,
            "reason": self.reason,
            "severity": self.severity,
        }


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    """The negotiation result for one request."""

    allowed: bool
    renderer: RendererInfo
    satisfied: tuple[str, ...] = ()
    downgrades: tuple[Downgrade, ...] = ()
    missing: tuple[CapabilityRequirement, ...] = ()

    @property
    def ok(self) -> bool:
        """Whether rendering may proceed. A hard miss blocks it."""
        return self.allowed

    def to_json(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "renderer": self.renderer.to_json(),
            "satisfied": list(self.satisfied),
            "downgrades": [d.to_json() for d in self.downgrades],
            "missing": [
                {"feature": m.feature, "strength": m.strength, "reason": m.reason}
                for m in self.missing
            ],
        }


@dataclass(frozen=True, slots=True)
class RenderRequest:
    """Everything a renderer needs, expressed in the document's terms."""

    # Either an HTML string or a path to one. Both forms appear in this
    # repository: diagram previews are rewritten in memory, templates are read
    # from disk.
    source: str
    base_url: Path
    output: Path
    requirements: tuple[CapabilityRequirement, ...] = ()
    # A strict request fails on a hard miss; a lenient one records and proceeds.
    # Strict is the default because a silent downgrade is the thing to avoid.
    strict: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def source_is_path(self) -> bool:
        return "\n" not in self.source and self.source.endswith(".html")


@dataclass(frozen=True, slots=True)
class RenderMetrics:
    """What the render cost, for the artifact manifest."""

    elapsed_ms: float | None = None
    pages: int | None = None
    peak_rss_mb: float | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.elapsed_ms is not None:
            out["elapsed_ms"] = round(self.elapsed_ms, 1)
        if self.pages is not None:
            out["pages"] = self.pages
        if self.peak_rss_mb is not None:
            out["peak_rss_mb"] = round(self.peak_rss_mb, 1)
        return out


@dataclass(frozen=True, slots=True)
class ArtifactSet:
    """What a render produced."""

    primary: Path
    auxiliary: tuple[Path, ...] = ()
    metrics: RenderMetrics = RenderMetrics()

    def to_json(self) -> dict[str, Any]:
        return {
            "primary": str(self.primary),
            "auxiliary": [str(p) for p in self.auxiliary],
            "metrics": self.metrics.to_json(),
        }


class RendererError(RuntimeError):
    """Raised when a render cannot proceed or fails."""


@runtime_checkable
class Renderer(Protocol):
    """The contract every engine implements.

    Held to four methods so a second engine is a contained piece of work
    rather than a rewrite. Anything an engine wants to expose beyond this
    belongs in an inspector, not in the renderer interface.
    """

    id: str
    api_version: str

    def probe(self) -> RendererInfo:
        """Report identity and capabilities. Called once, then cached."""
        ...

    def validate_request(self, request: RenderRequest) -> CapabilityReport:
        """Decide whether this request may render, and what it costs."""
        ...

    def render(self, request: RenderRequest) -> ArtifactSet:
        """Produce the artifacts. Raises `RendererError` on failure."""
        ...

    def inspect(self, artifacts: ArtifactSet) -> Mapping[str, Any]:
        """Read back measurable facts about what was produced."""
        ...


def negotiate(
    info: RendererInfo,
    requirements: tuple[CapabilityRequirement, ...],
    *,
    strict: bool = True,
) -> CapabilityReport:
    """Match requirements against capabilities.

    Kept separate from any engine so the rule is testable on its own and every
    renderer inherits the same behaviour.
    """
    satisfied: list[str] = []
    downgrades: list[Downgrade] = []
    missing: list[CapabilityRequirement] = []

    for requirement in requirements:
        level = info.level(requirement.feature)
        if level == "native":
            satisfied.append(requirement.feature)
            continue
        if level == "unsupported":
            missing.append(requirement)
            # A soft requirement that cannot be met is still a difference from
            # what the document asked for. Recording it here means the ledger
            # covers every degradation, not only the partial ones.
            if not requirement.is_hard:
                downgrades.append(
                    Downgrade(
                        feature=requirement.feature,
                        requested=requirement.reason,
                        resolved="not provided",
                        reason=f"{info.name} does not support {requirement.feature}",
                        severity="info",
                    )
                )
            continue
        # emulated or partial: the feature is met some other way, which is
        # exactly what must be written down.
        downgrades.append(
            Downgrade(
                feature=requirement.feature,
                requested=requirement.reason,
                resolved=f"{level} support",
                reason=f"{info.name} reports '{level}' for {requirement.feature}",
                severity="warning" if requirement.is_hard else "info",
            )
        )

    hard_misses = [m for m in missing if m.is_hard]
    allowed = not hard_misses or not strict

    if hard_misses and not strict:
        # Lenient mode still cannot pretend: the miss is recorded, and the
        # caller sees it in the report.
        downgrades.extend(
            Downgrade(
                feature=m.feature,
                requested=m.reason,
                resolved="not rendered",
                reason=f"{info.name} does not support {m.feature}",
                severity="warning",
            )
            for m in hard_misses
        )

    return CapabilityReport(
        allowed=allowed,
        renderer=info,
        satisfied=tuple(satisfied),
        downgrades=tuple(downgrades),
        missing=tuple(missing),
    )
