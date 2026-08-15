from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = ROOT / "references" / "schemas" / "types"


@dataclass(frozen=True)
class DiagramSchemaContract:
    kind: str
    schema_path: Path
    canonical_fixture: Path
    minimal_fixture: Path
    input_schema_version: str

    def load_schema(self) -> dict[str, Any]:
        return json.loads(self.schema_path.read_text(encoding="utf-8"))

    def load_canonical_payload(self) -> dict[str, Any]:
        return json.loads(self.canonical_fixture.read_text(encoding="utf-8"))

    def load_minimal_payload(self) -> dict[str, Any]:
        return json.loads(self.minimal_fixture.read_text(encoding="utf-8"))

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "schema": str(self.schema_path.relative_to(ROOT)),
            "canonical_fixture": str(self.canonical_fixture.relative_to(ROOT)),
            "minimal_fixture": str(self.minimal_fixture.relative_to(ROOT)),
            "input_schema_version": self.input_schema_version,
        }


def _contract(kind: str, fixture: str, version: str) -> DiagramSchemaContract:
    return DiagramSchemaContract(
        kind,
        SCHEMA_ROOT / f"{kind}.schema.json",
        ROOT / fixture,
        ROOT / "references" / "fixtures" / "minimal" / f"{kind}.json",
        version,
    )


SCHEMA_CONTRACTS: dict[str, DiagramSchemaContract] = {
    item.kind: item
    for item in (
        _contract("architecture", "references/fixtures/architecture-demo.json", "3.0"),
        _contract("flowchart", "references/fixtures/flowchart/branching.json", "2.0"),
        _contract("state-machine", "references/fixtures/v3/state-machine.json", "3.0"),
        _contract("swimlane", "references/fixtures/v3/swimlane.json", "3.0"),
        _contract("tree", "references/fixtures/v3/tree.json", "3.0"),
        _contract("layer-stack", "references/fixtures/v3/layer-stack.json", "3.0"),
        _contract("timeline", "references/fixtures/v3/timeline.json", "3.0"),
        _contract("quadrant", "references/fixtures/v3/quadrant.json", "3.0"),
        _contract("venn", "references/fixtures/v3/venn.json", "3.0"),
        _contract("pyramid", "references/fixtures/v5/pyramid.json", "3.0"),
        _contract("org-chart", "references/fixtures/v5/org-chart.json", "3.0"),
        _contract("loop-flywheel", "references/fixtures/v5/loop-flywheel.json", "3.0"),
        _contract("bar-chart", "references/fixtures/v3/bar-chart.json", "3.0"),
        _contract("line-chart", "references/fixtures/v3/line-chart.json", "3.0"),
        _contract("donut-chart", "references/fixtures/v3/donut-chart.json", "3.0"),
        _contract("candlestick", "references/fixtures/v3/candlestick.json", "3.0"),
        _contract("waterfall", "references/fixtures/v3/waterfall.json", "3.0"),
        _contract("scatter", "references/fixtures/v5/scatter.json", "3.0"),
        _contract("gantt", "references/fixtures/v5/gantt.json", "3.0"),
        _contract("sequence", "references/fixtures/v4/sequence.json", "3.0"),
        _contract("uml-class", "references/fixtures/v4/uml-class.json", "3.0"),
        _contract("er-diagram", "references/fixtures/v4/er-diagram.json", "3.0"),
    )
}


def schema_contract(kind: str) -> DiagramSchemaContract:
    try:
        return SCHEMA_CONTRACTS[kind]
    except KeyError as exc:
        raise ValueError(f"unknown diagram schema kind: {kind}") from exc


def list_schema_contracts() -> tuple[DiagramSchemaContract, ...]:
    return tuple(SCHEMA_CONTRACTS[kind] for kind in sorted(SCHEMA_CONTRACTS))
