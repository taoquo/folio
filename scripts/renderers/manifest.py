"""Artifact manifests: what produced this file, and from what.

A PDF on its own cannot answer "which engine, which fonts, which profiles, and
did anything degrade while making it". Without that answer a rendering change
cannot be attributed to a cause, and a capability downgrade cannot be found
after the fact.

The manifest is a first-class artifact, written beside every render.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_VERSION = "1.0"


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_value(value: Any) -> str:
    """A stable digest of a JSON-serialisable value."""
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def environment_fingerprint() -> dict[str, str]:
    """The parts of the machine that can change rendered output.

    Deliberately small: enough to tell whether two manifests are comparable,
    without recording anything that would differ for irrelevant reasons.
    """
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "executable": Path(sys.executable).name,
    }


@dataclass
class ArtifactManifest:
    """Provenance for one rendered artifact."""

    document_id: str
    renderer_name: str
    renderer_version: str
    primary: Path
    schema_version: str = MANIFEST_VERSION
    pages: int | None = None
    fonts: tuple[str, ...] = ()
    profiles: Mapping[str, str] = field(default_factory=dict)
    capabilities: Mapping[str, str] = field(default_factory=dict)
    downgrades: tuple[Mapping[str, Any], ...] = ()
    input_digest: str | None = None
    environment: Mapping[str, str] = field(default_factory=environment_fingerprint)
    metrics: Mapping[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # Set when a render was refused, so the record shows an attempt that did
    # not become an artifact rather than nothing at all.
    refused_reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "manifest_version": self.schema_version,
            "document_id": self.document_id,
            "renderer": {"name": self.renderer_name, "version": self.renderer_version},
            "artifact": {
                "path": str(self.primary),
                "sha256": sha256_file(self.primary),
                "pages": self.pages,
            },
            "fonts": list(self.fonts),
            "profiles": dict(sorted(self.profiles.items())),
            "capabilities": dict(sorted(self.capabilities.items())),
            "downgrades": [dict(d) for d in self.downgrades],
            "input": {"digest": self.input_digest},
            "environment": dict(self.environment),
            "metrics": dict(self.metrics),
            "generated_at": self.generated_at,
        }
        if self.refused_reason:
            payload["refused_reason"] = self.refused_reason
        return payload

    def write(self, path: Path | None = None) -> Path:
        target = path or self.primary.with_suffix(self.primary.suffix + ".manifest.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return target

    @property
    def degraded(self) -> bool:
        """Whether anything was met by means other than native support."""
        return bool(self.downgrades)

    def summary(self) -> str:
        parts = [f"{self.renderer_name} {self.renderer_version}"]
        if self.pages is not None:
            parts.append(f"{self.pages}p")
        parts.append(f"{len(self.fonts)} font(s)")
        if self.degraded:
            parts.append(f"{len(self.downgrades)} downgrade(s)")
        return ", ".join(parts)


def build_manifest(
    *,
    document_id: str,
    renderer_info: Any,
    artifact: Any,
    inspection: Mapping[str, Any] | None = None,
    profiles: Mapping[str, str] | None = None,
    capability_report: Any = None,
    input_value: Any = None,
) -> ArtifactManifest:
    """Assemble a manifest from what the render actually produced."""
    inspection = inspection or {}
    downgrades: tuple[Mapping[str, Any], ...] = ()
    if capability_report is not None:
        downgrades = tuple(d.to_json() for d in getattr(capability_report, "downgrades", ()))

    return ArtifactManifest(
        document_id=document_id,
        renderer_name=getattr(renderer_info, "name", "unknown"),
        renderer_version=getattr(renderer_info, "version", "unknown"),
        primary=artifact.primary,
        pages=inspection.get("pages") if inspection.get("pages") is not None else artifact.metrics.pages,
        fonts=tuple(inspection.get("fonts", ())),
        profiles=dict(profiles or {}),
        capabilities=dict(getattr(renderer_info, "capabilities", {})),
        downgrades=downgrades,
        input_digest=sha256_value(input_value) if input_value is not None else None,
        environment=environment_fingerprint(),
        metrics=artifact.metrics.to_json(),
    )
