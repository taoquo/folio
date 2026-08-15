from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .ledger import MAX_EDGES, MAX_NODES, ImportError_, Ledger, _clean_label, _slug, local_source

STYLE_SHAPES = (
    ("rhombus", "decision"),
    ("mxgraph.flowchart.decision", "decision"),
    ("ellipse", "terminal"),
    ("mxgraph.flowchart.terminator", "terminal"),
    ("mxgraph.flowchart.start", "terminal"),
    ("shape=document", "data"),
    ("shape=parallelogram", "data"),
    ("mxgraph.flowchart.data", "data"),
    ("shape=predefinedprocess", "subprocess"),
    ("mxgraph.flowchart.predefined_process", "subprocess"),
    ("double=1", "subprocess"),
)
DASHED_RE = re.compile(r"dashed=1")
IGNORED_STYLES = ("swimlane", "group", "shape=note", "text;", "edgeLabel")


def load_drawio_diagram(path: str | Path, *, base: Path | None = None) -> tuple[dict[str, Any], Ledger]:
    """Import a single-page draw.io flowchart as a Folio flowchart payload."""

    source = local_source(path, base=base or Path.cwd())
    text = source.read_text(encoding="utf-8")
    ledger = Ledger(source.name, "drawio", "flowchart")
    model, page_name = _model(text)
    root = model.find("root")
    if root is None:
        raise ImportError_("draw.io file has no <root> element")

    cells = [cell for cell in root.iter("mxCell")]
    nodes: dict[str, dict[str, Any]] = {}
    ids: dict[str, str] = {}
    labels: dict[str, str] = {}
    edge_cells: list[ET.Element] = []
    edge_labels: dict[str, str] = {}

    for cell in cells:
        style = cell.get("style") or ""
        value = _clean_label(cell.get("value") or "")
        cell_id = cell.get("id") or ""
        if cell.get("edge") == "1":
            edge_cells.append(cell)
            continue
        if cell.get("vertex") != "1":
            continue
        parent = cell.get("parent") or ""
        if value and parent and any(other.get("id") == parent and other.get("edge") == "1" for other in cells):
            edge_labels[parent] = value
            continue
        if any(token in style for token in IGNORED_STYLES):
            ledger.drop("container", style[:40])
            continue
        node_id = _slug(cell_id, ids)
        labels[cell_id] = value or node_id
        nodes[node_id] = {"id": node_id, "type": _shape(style), "label": (value or node_id)[:56]}

    if not nodes:
        raise ImportError_("draw.io file has no flowchart shapes")
    ledger.keep("shapes", str(len(nodes)))
    ledger.drop("geometry", "Folio recomputes deterministic layout")

    edges: list[dict[str, Any]] = []
    for cell in edge_cells:
        raw_source = cell.get("source")
        raw_target = cell.get("target")
        if not raw_source or not raw_target:
            ledger.drop("dangling edge", cell.get("id") or "")
            continue
        if raw_source not in ids or raw_target not in ids:
            ledger.drop("edge outside imported shapes", cell.get("id") or "")
            continue
        style = cell.get("style") or ""
        label = _clean_label(cell.get("value") or "") or edge_labels.get(cell.get("id") or "", "")
        kind = "sequence-flow"
        if label:
            kind = "conditional-flow"
        if DASHED_RE.search(style):
            kind = "exception-flow"
            ledger.downgrade("dashed edge", "mapped to exception-flow")
        edge: dict[str, Any] = {"source": ids[raw_source], "target": ids[raw_target], "kind": kind}
        if label:
            edge["label"] = label[:24]
        edges.append(edge)

    if not edges:
        raise ImportError_("draw.io flowchart has no connected edges")
    if len(nodes) > MAX_NODES:
        raise ImportError_(f"import exceeds {MAX_NODES} nodes; split the diagram before importing")
    if len(edges) > MAX_EDGES:
        raise ImportError_(f"import exceeds {MAX_EDGES} edges; split the diagram before importing")
    ledger.keep("edges", str(len(edges)))

    payload = {
        "schema_version": "2.0",
        "kind": "flowchart",
        "title": _title(source, page_name),
        "axis": "top-down",
        "nodes": list(nodes.values()),
        "edges": edges,
    }
    return payload, ledger


def _model(text: str) -> tuple[ET.Element, str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ImportError_(f"draw.io file is not valid XML: {exc}") from exc
    if root.tag == "mxGraphModel":
        return root, ""
    if root.tag != "mxfile":
        raise ImportError_("draw.io file must start with <mxfile> or <mxGraphModel>")
    pages = root.findall("diagram")
    if not pages:
        raise ImportError_("draw.io file has no <diagram> page")
    if len(pages) > 1:
        raise ImportError_("draw.io file has multiple pages; export one page before importing")
    page = pages[0]
    model = page.find("mxGraphModel")
    if model is None:
        if (page.text or "").strip():
            raise ImportError_("draw.io page is compressed; re-export with 'Uncompressed XML'")
        raise ImportError_("draw.io page has no <mxGraphModel>")
    return model, (page.get("name") or "").strip()


def _title(source: Path, page_name: str) -> str:
    if page_name:
        return page_name[:56]
    stem = source.stem.replace("-", " ").replace("_", " ").strip()
    return stem.title() if stem else "Imported Flowchart"


def _shape(style: str) -> str:
    lowered = style.lower()
    for token, role in STYLE_SHAPES:
        if token.lower() in lowered:
            return role
    return "step"
