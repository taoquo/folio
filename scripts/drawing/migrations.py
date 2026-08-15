from __future__ import annotations

from copy import deepcopy
from typing import Any


LATEST_INPUT_VERSIONS = {
    "architecture": "3.0",
    "flowchart": "2.0",
    "state-machine": "3.0",
    "swimlane": "3.0",
    "tree": "3.0",
    "layer-stack": "3.0",
    "timeline": "3.0",
    "quadrant": "3.0",
    "venn": "3.0",
    "pyramid": "3.0",
    "org-chart": "3.0",
    "loop-flywheel": "3.0",
    "bar-chart": "3.0",
    "line-chart": "3.0",
    "donut-chart": "3.0",
    "candlestick": "3.0",
    "waterfall": "3.0",
    "scatter": "3.0",
    "gantt": "3.0",
    "sequence": "3.0",
    "uml-class": "3.0",
    "er-diagram": "3.0",
}


def migrate_authoring_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize compatible authoring inputs to their public schema major."""
    if not isinstance(payload, dict):
        raise ValueError("diagram input must be an object")
    kind = payload.get("kind")
    if kind not in LATEST_INPUT_VERSIONS:
        raise ValueError(f"unknown or missing diagram kind: {kind}")
    migrated = deepcopy(payload)
    if kind == "architecture" and "composition" not in migrated:
        migrated.setdefault("schema_version", "3.0")
    version = migrated.get("schema_version")
    expected = "2.0" if kind == "architecture" and "composition" in migrated else LATEST_INPUT_VERSIONS[kind]
    if version != expected:
        raise ValueError(f"{kind} schema_version must be {expected}")
    return migrated
